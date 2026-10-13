"""The instance-wide pretix webhook, now resolved per edition through the
ticketing settings."""

import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from attendee.models import AttendeeProfile, PretixOrder
from tests.ticketing_ids import make_ticketing

URL = reverse("webhooks:pretix_webhook")


@pytest.fixture
def shop(conference):
    return make_ticketing(conference, organizer="flashlights", event_id="2025")


def payload(**overrides):
    data = {
        "notification_id": 123,
        "organizer": "flashlights",
        "event": "2025",
        "code": "ORDER123",
        "action": "pretix.event.order.paid",
    }
    data.update(overrides)
    return json.dumps(data)


def post(client, body, secret="hook-secret"):
    url = URL if secret is None else f"{URL}?secret={secret}"
    return client.post(url, data=body, content_type="application/json")


@pytest.mark.django_db
class TestRefusals:
    def test_post_only(self, client, shop):
        assert client.get(f"{URL}?secret=hook-secret").status_code == 405

    def test_secret_required(self, client, shop):
        response = post(client, payload(), secret=None)
        assert response.status_code == 400
        assert b"Missing required query parameter" in response.content

    def test_bad_bodies(self, client, shop):
        assert post(client, "not json").content == b"Invalid JSON"
        assert post(client, "[1]").content == b"Invalid pretix payload structure"
        response = post(client, json.dumps({"notification_id": 1}))
        assert response.content == b"Invalid pretix payload structure"
        response = post(client, payload(action="pretix.event.order.wrongaction"))
        assert response.content == b"Unsupported pretix action"

    def test_an_organizer_and_event_no_edition_takes(self, client, shop):
        for body in (payload(organizer="someone"), payload(event="2019")):
            response = post(client, body)
            assert response.status_code == 400
            assert b"No edition takes" in response.content

    def test_an_edition_without_an_api(self, client, shop):
        shop.api_token = ""
        shop.save()
        assert post(client, payload()).status_code == 400

    def test_wrong_secret(self, client, shop):
        assert post(client, payload(), secret="nope").status_code == 401


@pytest.mark.django_db
class TestOrders:
    @patch("speakers.pretix.PretixClient.get_order")
    def test_paid_order_is_recorded_with_its_profile(
        self, get_order, client, conference, shop, pretix_order_data
    ):
        get_order.return_value = pretix_order_data
        response = post(client, payload())
        # Queued; under the test settings the task runs inline.
        assert response.status_code == 202
        assert response.json() == {"queued": "ORDER123"}
        order = PretixOrder.objects.get(order_code="ORDER123")
        assert order.conference == conference
        assert order.email == pretix_order_data["email"]
        assert AttendeeProfile.objects.filter(order=order).exists()

    @patch("speakers.pretix.PretixClient.get_order")
    def test_existing_order_is_updated_and_a_cancelled_one_has_no_profile(
        self, get_order, client, conference, shop, pretix_order_data
    ):
        PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        get_order.return_value = dict(pretix_order_data, status="c")
        post(client, payload(action="pretix.event.order.canceled"))
        order = PretixOrder.objects.get(order_code="ORDER123")
        assert order.status == "c"
        assert not AttendeeProfile.objects.filter(order=order).exists()

    @patch("webhooks.views.sync_order_task.delay", side_effect=RuntimeError("down"))
    def test_queue_down(self, delay, client, shop):
        response = post(client, payload())
        assert response.status_code == 502
