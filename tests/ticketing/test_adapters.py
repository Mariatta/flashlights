"""The adapter interface and the Pretix adapter (decision 0012, stage 2)."""

import importlib
from decimal import Decimal
from unittest import mock

import pytest
from django.apps import apps
from django_celery_beat.models import PeriodicTask

from attendee.models import PretixOrder
from portal.models import Conference
from tests.ticketing_ids import CITY, NOT_ANONYMOUS, make_ticketing
from ticketing.adapters import (
    REGISTERED,
    Adapter,
    Registration,
    Status,
    adapter_for,
)
from ticketing.adapters.pretix import PretixAdapter, PretixClient
from ticketing.models import TicketingSettings
from ticketing.sync import sync
from ticketing.tasks import PollFailed, poll_registrations_task

fill_state = importlib.import_module(
    "attendee.migrations.0007_flashlights_registrations"
).fill_state


def raw(**overrides):
    data = {
        "code": "R1",
        "status": "p",
        "total": "25.00",
        "email": "ada@example.com",
        "event": "2025",
        "url": "https://pretix.example/orders/R1/",
        "datetime": "2026-05-01T10:00:00Z",
        "last_modified": "2026-05-02T10:00:00Z",
        "cancellation_date": None,
        "positions": [
            {
                "item": 11,
                "attendee_name": "",
                "attendee_email": "ada@example.com",
                "answers": [
                    {"question_identifier": CITY, "answer": "Lima"},
                    {
                        "question_identifier": "ANONQ001",
                        "option_identifiers": [NOT_ANONYMOUS],
                    },
                ],
            },
            {"item": 11, "attendee_name": "Ada", "answers": []},
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture
def adapter(conference):
    row = make_ticketing(conference, product_map={"11": "ticket", "12": "donation"})
    return PretixAdapter(row, client=object())


class TestStatuses:
    @pytest.mark.parametrize(
        "status,total,expected",
        [
            ("p", "25.00", Status.PAID),
            ("p", "0.00", Status.FREE),
            ("n", "25.00", Status.PENDING),
            ("e", "25.00", Status.CANCELLED),
            ("c", "25.00", Status.CANCELLED),
            ("?", "25.00", Status.PENDING),
        ],
    )
    @pytest.mark.django_db
    def test_pretix_codes_normalise(self, adapter, status, total, expected):
        registration = adapter.normalise(raw(status=status, total=total))
        assert registration.status == expected
        assert registration.provider_status == status
        assert registration.is_registered == (expected in REGISTERED)


@pytest.mark.django_db
class TestNormalise:
    def test_fields(self, adapter):
        registration = adapter.normalise(raw())
        assert registration.provider == "PRETIX" and registration.code == "R1"
        assert registration.amount == Decimal("25.00")
        assert registration.name == "Ada"  # the first named position
        assert registration.attendee_emails == ["ada@example.com"]
        assert registration.answers[0] == {
            "question": CITY,
            "answer": "Lima",
            "options": [],
        }
        assert registration.raw["code"] == "R1"

    def test_ticket_or_donation_from_the_product_map(self, adapter):
        assert adapter.normalise(raw()).kind == "ticket"
        donation = raw(positions=[{"item": 12, "answers": []}])
        assert adapter.normalise(donation).kind == "donation"
        mixed = raw(positions=[{"item": 11}, {"item": 12}])
        assert adapter.normalise(mixed).kind == "ticket"
        unmapped = raw(positions=[{"item": 99}])
        assert adapter.normalise(unmapped).kind == "ticket"

    def test_get_and_iterate_through_the_client(self, conference):
        class FakeClient:
            def get_order(self, code):
                return raw(code=code)

            def iter_orders(self, modified_since=None, email=None):
                self.asked = (modified_since, email)
                return iter([raw(code="A"), raw(code="B")])

        client = FakeClient()
        adapter = PretixAdapter(make_ticketing(conference), client=client)
        assert adapter.get("Z").code == "Z"
        assert [r.code for r in adapter.iter_registrations(since="t")] == ["A", "B"]
        assert client.asked == ("t", None)
        list(adapter.iter_registrations(email="a@b"))
        assert client.asked == (None, "a@b")


@pytest.mark.django_db
class TestRegistry:
    def test_adapter_for(self, conference):
        assert adapter_for(None) is None
        row = make_ticketing(conference)
        adapter = adapter_for(row)
        assert isinstance(adapter, PretixAdapter)
        assert isinstance(adapter.client, PretixClient)
        row.api_token = ""
        assert adapter_for(row) is None

    def test_the_base_class_is_an_interface(self, conference):
        base = Adapter(TicketingSettings(conference=conference))
        for call in (
            lambda: base.get("x"),
            lambda: base.iter_registrations(),
            lambda: base.normalise({}),
        ):
            with pytest.raises(NotImplementedError):
                call()
        assert Registration(provider="CSV", code="1", status="free").is_registered


@pytest.mark.django_db
class TestOrders:
    def test_unchanged_registration_moves_nothing(self, conference, adapter):
        order = PretixOrder(order_code="R1", conference=conference)
        order.from_registration(adapter.normalise(raw()))
        assert order.is_registered and order.is_anonymous is False
        order.email = "changed@example.com"
        order.from_registration(adapter.normalise(raw()))  # same stamp
        assert order.email == "changed@example.com"

    def test_backfill_from_pretix_codes(self, conference):
        for code, status, total in (
            ("P1", "p", 10),
            ("F1", "p", 0),
            ("C1", "c", 10),
            ("E1", "e", 10),
            ("N1", "n", 10),
            ("X1", None, 10),
        ):
            PretixOrder.objects.create(
                order_code=code, conference=conference, status=status, total=total
            )
        fill_state(apps, None)
        states = dict(PretixOrder.objects.values_list("order_code", "state"))
        assert states == {
            "P1": "paid",
            "F1": "free",
            "C1": "cancelled",
            "E1": "cancelled",
            "N1": "pending",
            "X1": "",
        }


@pytest.mark.django_db
class TestPolling:
    def test_polls_every_edition_with_an_api(self, conference):
        assert poll_registrations_task() == "No edition has a ticketing API set up"
        make_ticketing(conference)
        older = Conference.objects.create(year=2023, name="Older", slug="2023")
        make_ticketing(older)
        quiet = Conference.objects.create(year=2022, name="Quiet", slug="2022")
        make_ticketing(quiet, provider="CSV", api_token="")  # no API: skipped

        def fake(row, adapter):
            if row.conference == older:
                raise RuntimeError("down")
            return 2

        with mock.patch("ticketing.tasks.sync", side_effect=fake) as sync:
            with pytest.raises(PollFailed, match="Older"):
                poll_registrations_task()
            assert sync.call_count == 2
            sync.side_effect = lambda row, adapter: 2
            result = poll_registrations_task()
        assert "Flashlights 2025: 2 registration(s)" in result
        assert "Quiet" not in result

    def test_sync_records_and_advances(self, conference, pretix_order_data):
        row = make_ticketing(conference)

        class Fake(Adapter):
            def iter_registrations(self, since=None, email=None):
                self.since = since
                return iter(
                    [PretixAdapter(row, client=object()).normalise(pretix_order_data)]
                )

        adapter = Fake(row)
        assert sync(row, adapter) == 1 and adapter.since is None
        row.refresh_from_db()
        assert row.last_synced_at is not None
        assert PretixOrder.objects.get(order_code="ORDER123").is_registered

    def test_schedule_is_seeded_and_the_old_one_retired(self):
        poll = importlib.import_module("ticketing.migrations.0002_poll_schedule")
        PeriodicTask.objects.filter(name=poll.TASK_NAME).delete()
        old = PeriodicTask.objects.filter(name=poll.OLD_TASK_NAME)
        old.update(enabled=True)
        poll.seed(apps, None)
        task = PeriodicTask.objects.get(name=poll.TASK_NAME)
        assert task.task == poll.TASK_PATH and task.interval.every == 15
        assert not old.filter(enabled=True).exists()
        poll.unseed(apps, None)
        assert not PeriodicTask.objects.filter(name=poll.TASK_NAME).exists()

    def test_only_pretix_takes_webhooks(self, conference):
        assert PretixAdapter.supports_webhooks and not Adapter.supports_webhooks
