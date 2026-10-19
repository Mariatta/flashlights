"""Per-edition ticketing settings."""

import importlib
from io import StringIO
from unittest import mock

import pytest
from cryptography.fernet import Fernet
from django.apps import apps
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from portal.context_processors import features
from portal.models import Conference
from speakers import encryption
from tests.speakers.factories import make_settings
from tests.ticketing_ids import CITY, make_ticketing
from ticketing.admin import TicketingSettingsAdminForm
from ticketing.forms import parse_map
from ticketing.models import (
    Provider,
    TicketingSettings,
    carry_forward,
    has_api,
    is_set_up,
    ticketing_for,
)

copy_migration = importlib.import_module("ticketing.migrations.0001_initial")


def tickets_url(conference):
    return reverse("conference_tickets", args=[conference.pk])


def form_data(**overrides):
    data = {
        "provider": "PRETIX",
        "base_url": "https://pretix.example/api/v1/",
        "organizer": "flashlights",
        "event_id": "2025",
        "api_token": "tok",
        "webhook_secret": "hook",
        "question_lines": f"{CITY} = city\n# a comment\n\nQ2 = heard_about",
        "product_lines": "11 = ticket\n12 = donation",
        "anonymous_question": "ANON",
        "anonymous_answer": "YES",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestHelpers:
    def test_nothing_without_a_row(self, conference):
        assert ticketing_for(None) is None and ticketing_for(conference) is None
        assert has_api(conference) is False and is_set_up(conference) is False

    def test_with_a_row(self, conference):
        row = make_ticketing(conference)
        assert str(row) == f"Ticketing for {conference}"
        assert has_api(conference) and is_set_up(conference)


@pytest.mark.django_db
class TestTicketsPage:
    def test_superuser_only(self, client, portal_user, conference):
        client.force_login(portal_user)
        assert client.get(tickets_url(conference)).status_code in (302, 403)

    def test_get_shows_the_webhook_url_and_never_the_secrets(
        self, client, admin_user, conference
    ):
        make_ticketing(conference)
        client.force_login(admin_user)
        content = client.get(tickets_url(conference)).content.decode()
        assert reverse("speakers:pretix_webhook", args=[conference.slug]) in content
        assert "tok-secret" not in content and "hook-secret" not in content
        assert "QCITY001 = city" in content  # the map as lines
        # The edition form links here.
        edit = client.get(reverse("conference_edit", args=[conference.pk]))
        assert tickets_url(conference) in edit.content.decode()

    def test_save_creates_the_row_with_its_maps(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(tickets_url(conference), form_data())
        assert response.status_code == 302
        row = TicketingSettings.objects.get(conference=conference)
        assert row.question_map == {CITY: "city", "Q2": "heard_about"}
        assert row.product_map == {"11": "ticket", "12": "donation"}
        assert row.api_token == "tok" and row.has_api

    def test_blank_secrets_keep_the_stored_ones(self, client, admin_user, conference):
        make_ticketing(conference, base_url=form_data()["base_url"])
        client.force_login(admin_user)
        client.post(tickets_url(conference), form_data(api_token="", webhook_secret=""))
        row = TicketingSettings.objects.get(conference=conference)
        assert row.api_token == "tok-secret" and row.webhook_secret == "hook-secret"

    def test_an_unreadable_secret_is_refused_not_erased(
        self, client, admin_user, conference
    ):
        """A deploy without its key cannot read the token; saving the page
        must not write it empty."""
        make_ticketing(conference, base_url=form_data()["base_url"])
        client.force_login(admin_user)
        with override_settings(FERNET_KEY=Fernet.generate_key().decode()):
            encryption._warned = False
            response = client.post(
                tickets_url(conference), form_data(api_token="", webhook_secret="")
            )
            form = TicketingSettingsAdminForm(
                data={
                    "conference": conference.pk,
                    "provider": "PRETIX",
                    "base_url": form_data()["base_url"],
                },
                instance=TicketingSettings.objects.get(conference=conference),
            )
            assert not form.is_valid() and "api_token" in form.errors
        encryption._warned = False
        assert response.status_code == 200
        assert "cannot read the stored value" in response.content.decode()
        row = TicketingSettings.objects.get(conference=conference)
        assert row.api_token == "tok-secret" and row.webhook_secret == "hook-secret"

    def test_a_new_base_url_clears_the_stored_token(
        self, client, admin_user, conference
    ):
        """The token is never sent to a host it was not entered for."""
        make_ticketing(conference, base_url=form_data()["base_url"])
        client.force_login(admin_user)
        client.post(
            tickets_url(conference),
            form_data(
                api_token="",
                webhook_secret="",
                base_url="https://elsewhere.example/api/v1/",
            ),
        )
        row = TicketingSettings.objects.get(conference=conference)
        assert row.base_url == "https://elsewhere.example/api/v1/"
        assert row.api_token == "" and row.webhook_secret == "hook-secret"
        client.post(
            tickets_url(conference),
            form_data(
                api_token="new-tok", base_url="https://elsewhere.example/api/v1/"
            ),
        )
        assert (
            TicketingSettings.objects.get(conference=conference).api_token == "new-tok"
        )

    def test_refusals(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            tickets_url(conference),
            form_data(
                organizer="",
                question_lines="Q1 = shoe_size\nnot a line",
                product_lines="7 = raffle",
            ),
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Pretix needs this" in content
        assert "&#x27;shoe_size&#x27; is not one of an attendee field" in content
        assert "Line 2: write it as ID = an attendee field." in content
        assert "is not one of ticket or donation" in content
        assert not TicketingSettings.objects.filter(conference=conference).exists()

    def test_a_refused_card_stays_in_view(self, client, admin_user, conference):
        client.force_login(admin_user)
        page = client.get(tickets_url(conference)).content.decode()
        assert 'data-show-when="id_provider=CSV"' in page
        assert 'data-show-when="id_provider=PRETIX"' in page
        # Pretix chosen, a bad CSV map left behind: its card is not hidden.
        content = client.post(
            tickets_url(conference), form_data(csv_lines="not a line")
        ).content.decode()
        assert "write it as field = Column header" in content
        assert 'data-show-when="id_provider=CSV"' not in content
        assert 'data-show-when="id_provider=PRETIX"' in content
        content = client.post(
            tickets_url(conference), form_data(provider="CSV", base_url="nope")
        ).content.decode()
        assert 'data-show-when="id_provider=PRETIX"' not in content

    def test_csv_needs_no_shop(self, client, admin_user, conference):
        client.force_login(admin_user)
        client.post(
            tickets_url(conference),
            form_data(
                provider="CSV",
                organizer="",
                event_id="",
                api_token="",
                csv_lines="email = Email",
            ),
        )
        row = TicketingSettings.objects.get(conference=conference)
        assert row.is_set_up and not row.has_api

    def test_parse_map_skips_blanks_and_comments(self):
        assert parse_map("", {"a"}, "x") == {}
        assert parse_map(" # only a comment\n\n", {"a"}, "x") == {}


@pytest.mark.django_db
class TestCarryForward:
    def test_nothing_to_carry(self, conference):
        new = Conference.objects.create(year=2031, name="N", slug="2031")
        assert carry_forward(new, conference) is None
        assert carry_forward(new, None, "ev").event_id == "ev"

    def test_csv_columns_and_first_time_answer_come_along(self, conference):
        """A CSV edition imports next year without re-entering its columns,
        and keeps its first-time cards."""
        make_ticketing(
            conference,
            provider=Provider.CSV,
            csv_columns={"email": "Email address", "name": "Name"},
            first_time_answer="Yes",
        )
        new = Conference.objects.create(year=2033, name="N", slug="2033")
        row = carry_forward(new, conference)
        assert row.csv_columns == {"email": "Email address", "name": "Name"}
        assert row.first_time_answer == "Yes"

    def test_unreadable_secrets_stay_behind(self, conference):
        make_ticketing(conference)
        new = Conference.objects.create(year=2032, name="N", slug="2032")
        with override_settings(FERNET_KEY=Fernet.generate_key().decode()):
            encryption._warned = False
            row = carry_forward(new, conference, "2032")
        encryption._warned = False
        assert row.api_token == "" and row.webhook_secret == ""
        assert row.organizer == "flashlights" and row.event_id == "2032"


@pytest.mark.django_db
class TestCopyFromSpeakerSettings:
    def test_copies_configured_rows_once(self, conference):
        make_settings(
            conference,
            pretix_organizer="org",
            pretix_api_token="tok",
            pretix_webhook_secret="hook",
        )
        other = Conference.objects.create(year=2024, name="Old", slug="2024")
        make_settings(other)  # nothing to copy
        copy_migration.copy_speakers_pretix(apps, None)
        copy_migration.copy_speakers_pretix(apps, None)  # idempotent
        row = TicketingSettings.objects.get(conference=conference)
        assert (row.organizer, row.event_id) == ("org", conference.pretix_event_slug)
        assert row.api_token == "tok" and row.webhook_secret == "hook"
        assert not TicketingSettings.objects.filter(conference=other).exists()

    def test_unreadable_token_is_left_behind(self, conference):
        make_settings(conference, pretix_organizer="org", pretix_api_token="tok")
        with override_settings(FERNET_KEY=Fernet.generate_key().decode()):
            encryption._warned = False
            copy_migration.copy_speakers_pretix(apps, None)
        encryption._warned = False
        assert TicketingSettings.objects.get(conference=conference).api_token == ""


@pytest.mark.django_db
class TestAttendeesFlag:
    def test_follows_the_active_edition(self, rf, conference):
        assert not features(rf.get("/"))["pretix_configured"]
        make_ticketing(conference, provider="CSV", api_token="")
        assert features(rf.get("/"))["pretix_configured"]


@pytest.mark.django_db
class TestFetchCommand:
    def test_nothing_set_up(self, conference):
        out = StringIO()
        call_command("fetch_pretix_orders", stdout=out)
        assert "No edition has a Pretix API" in out.getvalue()

    def test_unknown_edition(self, conference):
        with pytest.raises(Exception, match="No edition 'nope'"):
            call_command("fetch_pretix_orders", conference="nope", stdout=StringIO())

    @mock.patch("attendee.management.commands.fetch_pretix_orders.reconcile")
    def test_reconciles_each_edition(self, reconcile, conference):
        row = make_ticketing(conference)
        row.last_synced_at = "2026-01-01T00:00:00Z"
        row.save()
        reconcile.return_value = 4
        out = StringIO()
        call_command(
            "fetch_pretix_orders", conference=conference.slug, full=True, stdout=out
        )
        reconcile.assert_called_once_with(conference)
        assert "4 order(s) synced" in out.getvalue()
        row.refresh_from_db()
        assert row.last_synced_at is None  # --full starts over
