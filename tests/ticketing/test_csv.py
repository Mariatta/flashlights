"""CSV import: the Maintainer Summit's
case, a registrant export from a shop the edition does not run."""

from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.urls import reverse

from attendee.models import AttendeeProfile, PretixOrder
from speakers.constants import AutoRule, ItemOwner, ItemStatus
from speakers.models import ChecklistItem
from tests.speakers.factories import make_presenter, make_settings
from tests.ticketing_ids import make_ticketing
from ticketing.adapters import CsvAdapter, Status
from ticketing.adapters.csv import parse_amount, parse_when
from ticketing.forms import parse_columns
from ticketing.sync import CsvImportError, import_csv

COLUMNS = {
    "email": "Email",
    "name": "Full name",
    "code": "Order",
    "status": "Status",
    "amount": "Paid",
    "created": "Date",
    "product": "Ticket",
}

EXPORT = """Order,Full name,Email,Status,Paid,Date,Ticket,City
A1,Ada Lovelace,ADA@example.com,Completed,$25.00,2026-04-01,Summit,London
A2,Grace Hopper,grace@example.com,Cancelled,25,2026-04-02T10:00:00,Summit,Arlington
A3,No Email,,Completed,0,,Summit,
A4,Free Person,free@example.com,,0,2026-04-03,Comp,Lima
"""


@pytest.fixture
def csv_ticketing(conference):
    return make_ticketing(
        conference,
        provider="CSV",
        api_token="",
        csv_columns=COLUMNS,
        question_map={"City": "city"},
        product_map={"Donation": "donation"},
    )


class TestParsing:
    def test_amounts(self):
        assert parse_amount("$1,250.50") == Decimal("1250.50")
        assert parse_amount("") == parse_amount("n/a") == Decimal("0")
        assert parse_amount("1.2.3") == Decimal("0")

    def test_dates(self):
        assert parse_when("") is None and parse_when("soon") is None
        assert parse_when("2026-02-30") is None
        assert parse_when("2026-04-01") == datetime(2026, 4, 1, tzinfo=UTC)
        assert parse_when("2026-04-01T10:00:00+02:00").utcoffset().seconds == 7200

    def test_columns(self):
        assert parse_columns("email = E-mail\n# note\n\n") == {"email": "E-mail"}
        with pytest.raises(Exception) as caught:
            parse_columns("shoe = Size\nemail")
        messages = caught.value.messages
        assert "'shoe' is not one of" in messages[0]
        assert "write it as field = Column header" in messages[1]


@pytest.mark.django_db
class TestAdapter:
    def test_normalise(self, csv_ticketing):
        adapter = CsvAdapter(csv_ticketing)
        row = {
            "Order": "A1",
            "Full name": "Ada",
            "Email": " ADA@example.com ",
            "Status": "Completed",
            "Paid": "$25.00",
            "Date": "2026-04-01",
            "Ticket": "Summit",
            "City": " London ",
        }
        registration = adapter.normalise(row)
        assert registration.code == "csv-2025-A1"
        assert registration.email == "ada@example.com"
        assert registration.status == Status.PAID
        assert registration.amount == Decimal("25.00")
        assert registration.kind == "ticket"
        assert registration.answers == [
            {"question": "City", "answer": "London", "options": []}
        ]
        assert adapter.normalise(dict(row, Ticket="Donation")).kind == "donation"

    def test_a_name_split_across_columns_is_joined(self, csv_ticketing):
        """PyCon US exports first and last name apart: name = First + Last."""
        csv_ticketing.csv_columns = {
            "email": "Email",
            "name": "First Name + Last Name",
        }
        row = {"Email": "dana@example.org", "First Name": "Dana", "Last Name": " Ruiz "}
        registration = CsvAdapter(csv_ticketing).normalise(row)
        assert registration.name == "Dana Ruiz"
        # Both columns are mapped, so neither is kept as an answer.
        assert registration.answers == []
        assert (
            CsvAdapter(csv_ticketing).normalise(dict(row, **{"Last Name": ""})).name
            == "Dana"
        )

    def test_importing_checks_each_joined_column(self, csv_ticketing):
        csv_ticketing.csv_columns = {
            "email": "Email",
            "name": "First Name + Last Name",
        }
        csv_ticketing.save()
        result = import_csv(
            csv_ticketing, "First Name,Last Name,Email\nDana,Ruiz,dana@example.org\n"
        )
        assert result.imported == 1
        with pytest.raises(CsvImportError, match="'Last Name'"):
            import_csv(csv_ticketing, "First Name,Email\nDana,dana@example.org\n")

    @pytest.mark.parametrize(
        "word,amount,expected",
        [
            ("", "10", Status.PAID),
            ("", "0", Status.FREE),
            ("Paid", "0", Status.FREE),
            ("free", "0", Status.FREE),
            ("Waitlist", "0", Status.PENDING),
            ("refunded", "10", Status.REFUNDED),
            ("canceled", "10", Status.CANCELLED),
            ("mystery", "10", Status.PENDING),
        ],
    )
    def test_statuses(self, csv_ticketing, word, amount, expected):
        adapter = CsvAdapter(csv_ticketing)
        row = {"Email": "a@b.c", "Status": word, "Paid": amount}
        assert adapter.normalise(row).status == expected

    def test_codes_fit(self, csv_ticketing):
        adapter = CsvAdapter(csv_ticketing)
        long_code = adapter.normalise({"Email": "x" * 120 + "@example.com"}).code
        assert long_code.startswith("csv-") and len(long_code) <= 100
        no_code = adapter.normalise({"Email": "a@b.c", "Order": ""})
        assert no_code.code == "csv-2025-a@b.c"

    def test_unmapped_columns_are_answers_and_a_bare_list_works(self, conference):
        row = make_ticketing(
            conference, provider="CSV", api_token="", csv_columns={"email": "Email"}
        )
        registration = CsvAdapter(row).normalise({"Email": "a@b.c", "Note": "hi"})
        # No amount column: nothing paid, so free, and registered either way.
        assert registration.status == Status.FREE and registration.is_registered
        assert registration.answers == [
            {"question": "Note", "answer": "hi", "options": []}
        ]


@pytest.mark.django_db
class TestImport:
    def test_imports_and_counts(self, conference, csv_ticketing):
        result = import_csv(csv_ticketing, EXPORT.encode("utf-8-sig"))
        assert (result.imported, result.registered) == (3, 2)
        assert result.skipped == [(4, "no email address")]
        ada = PretixOrder.objects.get(order_code="csv-2025-A1")
        assert (
            ada.provider == "CSV" and ada.is_registered and ada.name == "Ada Lovelace"
        )
        assert AttendeeProfile.objects.get(order=ada).city == "London"
        assert PretixOrder.objects.get(order_code="csv-2025-A2").state == "cancelled"
        assert PretixOrder.objects.get(order_code="csv-2025-A4").state == "free"

    def test_reimport_updates_and_removes_nobody(self, conference, csv_ticketing):
        import_csv(csv_ticketing, EXPORT)
        newer = "Order,Full name,Email,Status,Paid,Date,Ticket,City\n" + (
            "A2,Grace Hopper,grace@example.com,Completed,25,,Summit,Arlington\n"
        )
        import_csv(csv_ticketing, newer)
        assert PretixOrder.objects.get(order_code="csv-2025-A2").state == "paid"
        assert PretixOrder.objects.filter(conference=conference).count() == 3

    def test_refusals(self, conference, csv_ticketing):
        with pytest.raises(CsvImportError, match="UTF-8"):
            import_csv(csv_ticketing, "Email\nadé@x.org".encode("latin-1"))
        with pytest.raises(CsvImportError, match="no column named 'Date', 'Full name'"):
            import_csv(csv_ticketing, "Email,Order\na@b.c,1\n")
        csv_ticketing.csv_columns = {}
        with pytest.raises(CsvImportError, match="Map the email column"):
            import_csv(csv_ticketing, EXPORT)

    def test_an_imported_registration_ticks_the_speakers_line(
        self, conference, csv_ticketing
    ):
        make_settings(conference)
        presenter = make_presenter(conference, email="ada@example.com")
        item = ChecklistItem.objects.create(
            conference=conference,
            owner=ItemOwner.SPEAKER,
            title="Register for the event",
            presenter=presenter,
            auto_complete_rule=AutoRule.PRETIX_REGISTERED,
        )
        import_csv(csv_ticketing, EXPORT)
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE


@pytest.mark.django_db
class TestPages:
    def url(self, conference):
        return reverse("conference_tickets_import", args=[conference.pk])

    def test_needs_the_column_map(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.get(self.url(conference))
        assert response.url == reverse("conference_tickets", args=[conference.pk])

    def test_tickets_page_saves_the_columns(self, client, admin_user, conference):
        client.force_login(admin_user)
        url = reverse("conference_tickets", args=[conference.pk])
        data = {
            "provider": "CSV",
            "base_url": "https://pretix.eu/api/v1/",
            "csv_lines": "name = Full name",
        }
        response = client.post(url, data)
        assert "Name the email column" in response.content.decode()
        data["csv_lines"] = "email = Email\nname = Full name"
        client.post(url, data)
        content = client.get(url).content.decode()
        assert "email = Email" in content
        assert self.url(conference) in content

    def test_upload(self, client, admin_user, conference, csv_ticketing):
        client.force_login(admin_user)
        assert (
            "<code>Full name</code>"
            in client.get(self.url(conference)).content.decode()
        )
        upload = SimpleUploadedFile("export.csv", EXPORT.encode(), "text/csv")
        response = client.post(self.url(conference), {"file": upload}, follow=True)
        content = response.content.decode()
        assert "Imported 3 row(s), 2 registered." in content
        assert "Line 4 skipped: no email address." in content
        bad = SimpleUploadedFile("bad.csv", b"Email\na@b.c\n", "text/csv")
        response = client.post(self.url(conference), {"file": bad})
        assert "no column named" in response.content.decode()

    def test_many_skipped_lines_are_summarised(
        self, client, admin_user, conference, csv_ticketing
    ):
        csv_ticketing.csv_columns = {"email": "Email"}
        csv_ticketing.save()
        rows = "Email\n" + "nobody\n" * 12
        client.force_login(admin_user)
        upload = SimpleUploadedFile("e.csv", rows.encode(), "text/csv")
        content = client.post(
            self.url(conference), {"file": upload}, follow=True
        ).content.decode()
        assert "2 more line(s) skipped." in content


@pytest.mark.django_db
class TestCommand:
    def test_refusals(self, conference, tmp_path):
        path = tmp_path / "e.csv"
        path.write_text(EXPORT)
        with pytest.raises(CommandError, match="No edition"):
            call_command("import_registrations", "nope", str(path))
        with pytest.raises(CommandError, match="Tickets page"):
            call_command("import_registrations", conference.slug, str(path))
        make_ticketing(conference, provider="CSV", api_token="")
        with pytest.raises(CommandError, match="Map the email column"):
            call_command("import_registrations", conference.slug, str(path))

    def test_imports(self, conference, csv_ticketing, tmp_path):
        path = tmp_path / "e.csv"
        path.write_text(EXPORT)
        out = StringIO()
        call_command("import_registrations", conference.slug, str(path), stdout=out)
        assert "Line 4 skipped" in out.getvalue()
        assert "3 row(s) imported, 2 registered" in out.getvalue()
