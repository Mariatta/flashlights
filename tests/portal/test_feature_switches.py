"""``SPONSORSHIP_ENABLED`` and ``STATS_PUBLIC``, with the stats sections
following the features (and the active edition's ticketing)."""

import pytest
from django.test import override_settings
from django.urls import reverse

from attendee.models import PretixOrder
from tests.speakers.factories import make_presenter, make_proposal, make_session
from tests.ticketing_ids import make_ticketing
from ticketing.models import TicketingSettings

STATS_PAGES = (
    "portal_stats",
    "portal_stats_comparison",
    "portal_stats_json",
)


@pytest.mark.django_db
class TestStatsPublic:
    def test_pages_answer_404_when_off(self, client, conference):
        with override_settings(STATS_PUBLIC=False):
            for name in STATS_PAGES:
                assert client.get(reverse(name)).status_code == 404, name
        for name in STATS_PAGES:
            assert client.get(reverse(name)).status_code == 200, name

    def test_nav_link_follows(self, client, conference):
        with override_settings(STATS_PUBLIC=False):
            assert reverse("portal_stats") not in client.get("/").content.decode()
        assert reverse("portal_stats") in client.get("/").content.decode()


@pytest.mark.django_db
class TestSponsorshipEnabled:
    def test_sponsorship_pages_answer_404_when_off(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        with override_settings(SPONSORSHIP_ENABLED=False):
            assert (
                client.get(reverse("sponsorship:sponsorship_list")).status_code == 404
            )
        assert client.get(reverse("sponsorship:sponsorship_list")).status_code == 200

    def test_organizer_pages_hide_sponsorship(self, client, admin_user, conference):
        conference.sponsors_url = "https://2025.example.org/sponsors/"
        conference.save()
        client.force_login(admin_user)
        with override_settings(SPONSORSHIP_ENABLED=False):
            dashboard = client.get(reverse("organizer_dashboard")).content.decode()
        assert "Manage sponsors" not in dashboard
        assert "Add sponsor" not in dashboard
        assert reverse("sponsorship:sponsorship_list") not in dashboard
        assert "Sponsorship resources" not in dashboard
        assert "Donations" not in dashboard  # the goal tile
        dashboard = client.get(reverse("organizer_dashboard")).content.decode()
        assert "Manage sponsors" in dashboard and "Donations" in dashboard

    def test_public_pages_hide_sponsorship(self, client, conference):
        conference.sponsors_url = "https://2025.example.org/sponsors/"
        conference.donate_url = "https://2025.example.org/donate/"
        conference.save()
        with override_settings(SPONSORSHIP_ENABLED=False):
            landing = client.get("/").content.decode()
            stats = client.get(reverse("portal_stats")).content.decode()
        assert "Sponsorship prospectus" not in landing
        assert "Sponsor us" not in stats and "Donate" not in stats
        landing = client.get("/").content.decode()
        assert "Sponsorship prospectus" in landing

    def test_comparison_charts_follow_the_features(self, client, conference):
        def ids(**flags):
            with override_settings(**flags):
                response = client.get(reverse("portal_stats_comparison"))
            return {c["chart_id"] for c in response.context["historical_comparison"]}

        # Each chart shows only where its metric has a source: nothing on a
        # fresh instance with sponsorship off.
        assert ids(SPONSORSHIP_ENABLED=False) == set()
        conference.proposals_count = 12  # proposals collected elsewhere
        conference.save()
        assert ids(SPONSORSHIP_ENABLED=False) == {"proposals_comparison"}
        # Registrations: ticketing set up on an edition, even before any order
        # is read; an edition from before the portal with a snapshot; or orders.
        # A row carried forward with only an event id is not set up.
        TicketingSettings.objects.create(
            conference=conference, event_id=conference.slug
        )
        assert "registrations_comparison" not in ids(SPONSORSHIP_ENABLED=False)
        make_ticketing(conference)
        assert "registrations_comparison" in ids(SPONSORSHIP_ENABLED=False)
        TicketingSettings.objects.all().delete()
        assert "registrations_comparison" not in ids(SPONSORSHIP_ENABLED=False)
        past = type(conference).objects.create(
            year=2019,
            name="Flashlights 2019",
            slug="2019",
            historical_snapshot={"registrations": 500},
        )
        assert "registrations_comparison" in ids(SPONSORSHIP_ENABLED=False)
        past.historical_snapshot = {"registrations": 0}  # frozen, but had none
        past.save()
        assert "registrations_comparison" not in ids(SPONSORSHIP_ENABLED=False)
        past.delete()
        PretixOrder.objects.create(order_code="R1", conference=conference)
        everything = ids(SPONSORSHIP_ENABLED=True)
        assert "proposals_comparison" in everything
        assert "sponsors_comparison" in everything
        assert "registrations_comparison" in everything

    def test_proposals_taken_here_compare(self, client, conference):
        make_proposal(make_session(conference), make_presenter(conference))
        response = client.get(reverse("portal_stats_comparison"))
        assert {c["chart_id"] for c in response.context["historical_comparison"]} >= {
            "proposals_comparison"
        }


@pytest.mark.django_db
class TestStatsSectionsFollowTheFeatures:
    def test_sections(self, client, conference):
        with override_settings(VOLUNTEERING_ENABLED=False, SPONSORSHIP_ENABLED=False):
            content = client.get(reverse("portal_stats")).content.decode()
        assert "Volunteers signed up" not in content
        assert "attendee_demographic" not in content
        assert "sponsorship_breakdown" not in content and "Sponsorship" not in content
        make_ticketing(conference)  # the active edition takes registrations
        content = client.get(reverse("portal_stats")).content.decode()
        assert "Volunteers signed up" in content
        assert "attendee_demographic" in content

    def test_snapshot_cards_follow_the_features(self, client, conference):
        conference.is_active = False
        conference.save()
        past = type(conference).objects.create(
            year=2024,
            name="Flashlights 2024",
            slug="2024",
            historical_snapshot={
                "registrations": 500,
                "sponsors": 7,
                "sponsorship_amount": 12000,
                "donors": 40,
                "donation_amount": 900,
            },
        )
        url = reverse("portal_stats") + f"?year={past.year}"
        with override_settings(SPONSORSHIP_ENABLED=False):
            content = client.get(url).content.decode()
        assert "Final numbers" in content
        # Recorded registrations stand on their own; the sponsor and money
        # cards follow the sponsorship switch.
        assert "500" in content
        assert "12000" not in content and "Sponsors" not in content
        with override_settings(SPONSORSHIP_ENABLED=True):
            content = client.get(url).content.decode()
        assert "12000" in content and "Sponsors" in content
