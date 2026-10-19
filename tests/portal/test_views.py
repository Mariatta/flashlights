import re
from datetime import date

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from portal import branding
from portal.models import Conference, Venue
from portal_account.models import PortalProfile
from speakers.constants import EventFormat, ProposalDecision, Recordings
from speakers.models import ChecklistTemplate, SpeakerSettings
from speakers.seeds import seed_new_edition
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from tests.speakers.factories import make_presenter, make_proposal, make_session
from tests.ticketing_ids import make_ticketing
from ticketing.models import TicketingSettings
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile


def title_of(html):
    """The page's <title>, whitespace collapsed."""
    match = re.search(r"<title>(.*?)</title>", html, re.S)
    return " ".join(match.group(1).split())


@pytest.mark.django_db
class TestPortalIndex:

    def test_index_unauthenticated(self, client):

        response = client.get(reverse("index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Sign up" in content
        assert reverse("account_login") in content  # the navbar's Sign in

    def test_index_survives_no_active_conference(self, client):
        # It is valid to have no active edition; the public landing must not 500
        # (regression: get_stats_cached_values dereferenced conference.year).
        Conference.objects.all().delete()
        response = client.get(reverse("index"))
        assert response.status_code == 200

    def test_public_landing_sections_and_real_numbers(self, client, conference):
        with override_settings(
            BRAND=branding.from_env({"DOCS_URL": "https://docs.example.org/"})
        ):
            response = client.get(reverse("index"))
        assert response.status_code == 200
        content = response.content.decode()
        # Nothing leads: the name and description, then one section per way
        # to take part. Volunteering is one of them on this instance.
        assert settings.BRAND.title in content
        assert "Sign up to volunteer" in content
        # Team descriptions live on the docs site, so the link needs one.
        assert "Read the team descriptions" in content
        assert (
            "Read the team descriptions"
            not in client.get(reverse("index")).content.decode()
        )
        # No running totals on the landing: the band was a PyLadiesCon artifact.
        assert "Across all editions" not in content
        assert "landing-stats" not in content

    def test_landing_footer_shows_grouped_resources(self, client, conference):
        conference.coc_url = "https://example.org/coc/"
        conference.save()
        conference.coc_url = "https://2025.example.org/coc/"
        conference.save()
        with override_settings(
            BRAND=branding.from_env({"DOCS_URL": "https://docs.example.org/"})
        ):
            content = client.get(reverse("index")).content.decode()
        # The role-grouped external reference links live in the footer.
        assert "footer-heading" in content  # footer-only marker
        assert 'href="https://docs.example.org/">Documentation</a>' in content
        assert "Code of Conduct" in content

    def test_inner_page_keeps_minimal_footer(self, client, conference):
        # Pages that don't opt into footer_resources keep the minimal footer.
        content = client.get(reverse("portal_stats")).content.decode()
        assert "footer-heading" not in content

    def test_landing_never_counts_signups(self, client, portal_user, conference):
        # The "join N volunteers who signed up" line was a PyLadiesCon
        # artifact: the landing does not advertise a running total.
        VolunteerProfile.objects.create(user=portal_user, conference=conference)
        content = client.get(reverse("index")).content.decode()
        assert "already signed up" not in content
        assert "Sign up to volunteer" in content

    def test_landing_says_when_and_where(self, client, conference):
        conference.conference_date = None
        conference.save()
        content = client.get(reverse("index")).content.decode()
        assert "landing-where" not in content  # nothing to say yet
        conference.conference_date = date(2026, 5, 16)
        conference.venue = Venue.objects.create(
            name="Long Beach Convention Center", url="https://maps.example.org/lbcc"
        )
        conference.save()
        content = client.get(reverse("index")).content.decode()
        assert "16 May 2026" in content
        assert (
            '<a href="https://maps.example.org/lbcc">Long Beach Convention Center</a>'
            in content
        )
        # A multi-day edition shows the span; the list page shows the venue.
        conference.end_date = date(2026, 5, 17)
        conference.venue.url = ""
        conference.venue.save()
        conference.save()
        content = client.get(reverse("index")).content.decode()
        assert "16 May to 17 May 2026" in content
        assert "Long Beach Convention Center" in content

    def test_landing_title_is_the_instance_name(self, client, conference):
        content = client.get(reverse("index")).content.decode()
        assert title_of(content) == settings.BRAND.title

    def test_inner_page_title_carries_the_short_name(self, client):
        content = client.get(reverse("account_login")).content.decode()
        assert title_of(content) == f"Sign in | {settings.BRAND.short_name}"

    def test_navbar_shows_active_conference_year(self, client, conference):
        response = client.get(reverse("index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Active event edition" in content  # the navbar badge
        assert str(conference.year) in content

    @pytest.mark.no_agreements
    def test_index_authenticated_no_profile_created(self, client, portal_user):
        """An account with no profile has not agreed either, so the gate
        (portal_account.agreements) takes it before the index does."""
        client.force_login(portal_user)
        response = client.get(reverse("index"), follow=True)

        assert reverse("account_login") not in response.content.decode()
        assertRedirects(response, reverse("portal_account:agreements"))

    def test_index_authenticated_profile_already_created(self, client, portal_user):
        # Volunteers land on their hub, not a second portal landing page.
        portal_profile = PortalProfile(user=portal_user)
        portal_profile.save()

        client.force_login(portal_user)
        response = client.get(reverse("index"))
        assertRedirects(response, reverse("volunteer:index"))

    def test_organizer_redirected_to_dashboard(self, client, admin_user, conference):
        PortalProfile.objects.create(user=admin_user)
        client.force_login(admin_user)
        response = client.get(reverse("index"))
        assertRedirects(response, reverse("organizer_dashboard"))

    def test_non_organizer_redirected_to_volunteer_hub(
        self, client, portal_user, conference
    ):
        PortalProfile.objects.create(user=portal_user)
        client.force_login(portal_user)
        response = client.get(reverse("index"))
        assertRedirects(response, reverse("volunteer:index"))


@pytest.mark.django_db
class TestPageNotFound:
    """The 404 is a portal page with the navbar, so a wrong address is
    never a dead end: a visitor can sign in, a signed-in user can sign out."""

    def test_visitor_sees_the_navbar(self, client):
        response = client.get("/no-such-page/")
        assert response.status_code == 404
        content = response.content.decode()
        assert "Page not found" in content
        assert reverse("account_login") in content and reverse("index") in content

    def test_signed_in_user_can_sign_out(self, client, portal_user):
        PortalProfile.objects.create(user=portal_user)
        client.force_login(portal_user)
        response = client.get("/no-such-page/")
        assert response.status_code == 404
        assert "Sign out" in response.content.decode()


@pytest.mark.django_db
class TestPortalStats:

    def test_stats_doesnt_require_login(self, client):
        response = client.get(reverse("portal_stats"))
        assert response.status_code == 200
        assert "stats and numbers" in response.content.decode()

    def test_stats_survives_no_active_conference(self, client):
        # No active edition must render the stats page, not 500.
        Conference.objects.all().delete()
        response = client.get(reverse("portal_stats"))
        assert response.status_code == 200

    def test_stats_defaults_to_active_conference(self, client, conference):
        response = client.get(reverse("portal_stats"))
        assert response.status_code == 200
        assert response.context["selected_conference"] == conference

    def test_stats_year_switcher_selects_requested_year(self, client, conference):
        past = Conference.objects.create(
            year=2024, name="Flashlights 2024", slug="2024"
        )
        response = client.get(reverse("portal_stats") + "?year=2024")
        assert response.status_code == 200
        assert response.context["selected_conference"] == past

    def test_stats_invalid_year_falls_back_to_active(self, client, conference):
        response = client.get(reverse("portal_stats") + "?year=9999")
        assert response.status_code == 200
        assert response.context["selected_conference"] == conference

    def test_stats_historical_year_renders_snapshot(self, client, conference):
        Conference.objects.create(
            year=2024,
            name="Flashlights 2024",
            slug="2024",
            proposals_count=164,
            historical_snapshot={
                "registrations": 600,
                "sponsors": 8,
                "sponsorship_amount": 10500,
                "donors": 58,
                "donation_amount": 650,
            },
        )
        response = client.get(reverse("portal_stats") + "?year=2024")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Final numbers" in content
        assert "600" in content  # snapshot registrations
        assert "164" in content  # proposals_count

    def test_stats_count_the_portals_proposals_unless_typed_in(
        self, client, conference
    ):
        """A call for proposals run in the portal counts itself; one run
        elsewhere keeps the number organizers typed in."""
        session = make_session(conference)
        presenter = make_presenter(conference)
        make_proposal(session, presenter)
        make_proposal(
            make_session(conference),
            presenter,
            decision=ProposalDecision.WITHDRAWN,
        )
        url = reverse("portal_stats") + f"?year={conference.year}"
        assert client.get(url).context["proposals"] == 1
        conference.proposals_count = 192
        conference.save()
        assert client.get(url).context["proposals"] == 192

    def test_stats_currency_figures_dont_wrap(self, client, conference):
        # Large currency amounts (e.g. $54,805) must stay on one line.
        content = client.get(reverse("portal_stats")).content.decode()
        assert "sponsors contacted" in content  # the live stats panel rendered
        assert "stat-value text-nowrap" in content

    def test_stats_comparison_page_is_public(self, client, conference):
        response = client.get(reverse("portal_stats_comparison"))
        assert response.status_code == 200
        assert "Year-over-Year Comparison" in response.content.decode()


@pytest.mark.django_db
class TestStatsJSON:

    def test_stats_json_endpoint(self, client):
        """Test that the stats JSON endpoint returns the expected data.

        Actual stats values are tested in test_common.py.
        This is just testing that the endpoint is reachable and returns a JSON response.
        """
        response = client.get(reverse("portal_stats_json"))
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data

    def test_stats_json_accepts_year(self, client, conference):
        Conference.objects.create(year=2024, name="Flashlights 2024", slug="2024")
        response = client.get(reverse("portal_stats_json") + "?year=2024")
        assert response.status_code == 200
        assert "stats" in response.json()


@pytest.mark.django_db
class TestNoDashboardGallery:

    def test_gallery_page_and_stats_link_are_gone(self, client, conference):
        assert client.get("/dashboard_gallery").status_code == 404
        assert (
            "Dashboard Gallery"
            not in client.get(reverse("portal_stats")).content.decode()
        )


@pytest.mark.django_db
class TestStartNewYear:
    def test_requires_admin(self, client, portal_user):
        client.force_login(portal_user)  # not staff/superuser
        response = client.get(reverse("start_new_year"))
        assert response.status_code in (302, 403)

    def test_staff_non_superuser_denied(self, client, django_user_model, conference):
        # The wizard is superuser-only, so plain staff cannot reach it.
        staff = django_user_model.objects.create_user("staffy", is_staff=True)
        client.force_login(staff)
        response = client.get(reverse("start_new_year"))
        assert response.status_code in (302, 403)

    def test_get_renders_form_with_source(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.get(reverse("start_new_year"))
        assert response.status_code == 200
        assert response.context["source"] == conference  # most recent edition

    def test_form_marks_required_fields(self, client, admin_user, conference):
        client.force_login(admin_user)
        content = client.get(reverse("start_new_year")).content.decode()
        # Legend explains the asterisk; required fields carry the wrapper class
        # that the stylesheet turns into a "*" marker.
        assert "Fields marked with * are required" in content
        assert 'class="mb-3 required"' in content

    def test_creates_carries_over_and_activates(self, client, admin_user, conference):
        conference.sponsorship_goal = 15000
        conference.donation_goal = 2500
        conference.save()
        Team.objects.create(conference=conference, short_name="Comms", description="c")
        SponsorshipTier.objects.create(
            conference=conference, name="Gold", amount=1000, description="g"
        )
        vol = User.objects.create(username="returner")
        VolunteerProfile.objects.create(
            user=vol,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        client.force_login(admin_user)

        response = client.post(
            reverse("start_new_year"),
            {
                "year": 2026,
                "name": "Flashlights 2026",
                "slug": "2026",
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "clone_teams": "on",
                "copy_tiers": "on",
                "copy_goals": "on",
                "bring_volunteers": "on",
                "activate": "on",
            },
            follow=True,
        )

        assert response.status_code == 200
        new = Conference.objects.get(year=2026)
        assert new.is_active is True
        assert new.sponsorship_goal == 15000
        assert new.donation_goal == 2500
        assert new.teams.count() == 1
        assert new.sponsorship_tiers.count() == 1
        assert new.volunteer_profiles.filter(user=vol).exists()
        # single-active enforcer demoted the previous edition
        conference.refresh_from_db()
        assert conference.is_active is False

    def test_creates_without_previous_edition(self, client, admin_user, conference):
        # No prior edition to carry from.
        Conference.objects.all().delete()
        client.force_login(admin_user)

        response = client.post(
            reverse("start_new_year"),
            {
                "year": 2027,
                "name": "Flashlights 2027",
                "slug": "2027",
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "clone_teams": "on",
                "copy_tiers": "on",
                "copy_goals": "on",
            },
            follow=True,
        )

        assert response.status_code == 200
        new = Conference.objects.get(year=2027)
        assert new.is_active is False
        assert new.teams.count() == 0
        assert new.sponsorship_tiers.count() == 0

    def test_creates_with_dates_and_pretix(self, client, admin_user, conference):
        client.force_login(admin_user)
        client.post(
            reverse("start_new_year"),
            {
                "year": 2028,
                "name": "Flashlights 2028",
                "slug": "2028",
                "cadence": "ONCE",
                "conference_date": "2028-12-02",
                "end_date": "2028-12-03",
                "pretix_event_slug": "2028",
            },
            follow=True,
        )
        new = Conference.objects.get(year=2028)
        # The start date mirrors the event date: the schedule offers the run.
        assert str(new.start_date) == "2028-12-02"
        assert str(new.end_date) == "2028-12-03"
        assert str(new.conference_date) == "2028-12-02"
        # The event slug lands on the edition's ticketing row.
        assert new.ticketing.event_id == "2028"

    def test_carries_the_ticketing_forward(self, client, admin_user, conference):
        make_ticketing(conference, product_map={"7": "donation"})
        client.force_login(admin_user)
        client.post(
            reverse("start_new_year"),
            {
                "year": 2029,
                "name": "Next",
                "slug": "2029",
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "pretix_event_slug": "2029",
            },
        )
        row = Conference.objects.get(year=2029).ticketing
        assert row.event_id == "2029" and row.organizer == "flashlights"
        assert row.product_map == {"7": "donation"}

    def test_new_year_without_ticketing_has_none(self, client, admin_user, conference):
        client.force_login(admin_user)
        client.post(
            reverse("start_new_year"),
            {
                "year": 2030,
                "name": "N",
                "slug": "2030",
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
            },
        )
        assert not TicketingSettings.objects.filter(conference__year=2030).exists()

    def test_duplicate_year_rejected(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            reverse("start_new_year"),
            {
                "year": conference.year,
                "name": "Dup",
                "slug": "dup",
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
            },
        )
        assert response.status_code == 200  # re-renders with errors
        assert not Conference.objects.filter(slug="dup").exists()

    def test_duplicate_slug_rejected(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            reverse("start_new_year"),
            {"year": 2099, "name": "Dup", "slug": conference.slug},
        )
        assert response.status_code == 200  # re-renders with errors
        assert not Conference.objects.filter(year=2099).exists()


@pytest.mark.django_db
class TestStartNextYearGate:
    def test_wizard_blocked_once_the_next_edition_exists(
        self, client, admin_user, conference
    ):
        Conference.objects.create(
            year=conference.year + 1, name="Next", slug="next-edition"
        )
        client.force_login(admin_user)
        response = client.get(reverse("start_new_year"))
        assert response.url == reverse("index")
        page = client.get(reverse("organizer_dashboard")).content.decode()
        assert "The next edition already exists" in page

    def test_card_shown_while_the_edition_runs(self, client, admin_user, conference):
        # The current edition's date has not come yet: planning the next
        # one need not wait for it.
        conference.conference_date = None
        conference.save()
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert "Start next year" in response.content.decode()

    def test_card_hidden_once_the_next_edition_exists(
        self, client, admin_user, conference
    ):
        Conference.objects.create(
            year=conference.year + 1, name="Next", slug="next-edition"
        )
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert "Start next year" not in response.content.decode()


@pytest.mark.django_db
class TestOrganizeRail:
    """The shared Organize rail and the collapsed top-nav Organize link."""

    def _active_href(self, content, url):
        flat = " ".join(content.split())
        return f'active" href="{url}"' in flat

    def test_dashboard_shows_rail_dashboard_active(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert 'id="appSidebar"' in content
        assert self._active_href(content, reverse("organizer_dashboard"))
        # Sponsorship is one click away from the dashboard.
        assert reverse("sponsorship:sponsorship_list") in content
        assert reverse("sponsorship:tier_list") in content

    def test_conference_list_shows_rail_conferences_active(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        content = client.get(reverse("conference_list")).content.decode()
        assert 'id="appSidebar"' in content
        assert self._active_href(content, reverse("conference_list"))
        assert not self._active_href(content, reverse("organizer_dashboard"))

    def test_top_nav_organize_collapses_to_single_link(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        # The dropdown is gone; the rail carries the detailed navigation.
        assert 'id="navOrganize"' not in content

    def test_regular_user_gets_no_organize_link(self, client, portal_user, conference):
        client.force_login(portal_user)
        content = client.get(reverse("volunteer:index")).content.decode()
        assert reverse("organizer_dashboard") not in content


@pytest.mark.django_db
class TestConferenceCRUD:
    def test_list_shows_conferences(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.get(reverse("conference_list"))
        assert response.status_code == 200
        assert conference in response.context["conferences"]

    def test_list_puts_the_newest_first(self, client, admin_user, conference):
        for year in (2021, conference.year + 2, 2019):
            Conference.objects.create(
                year=year, name=f"Edition {year}", slug=f"e{year}"
            )
        client.force_login(admin_user)
        conferences = client.get(reverse("conference_list")).context["conferences"]
        assert conferences.ordered
        years = [edition.year for edition in conferences]
        assert years == sorted(years, reverse=True)

    def test_list_shows_start_button_when_edition_over(
        self, client, admin_user, conference
    ):
        conference.conference_date = "2000-01-01"  # past -> next year can start
        conference.save()
        client.force_login(admin_user)
        response = client.get(reverse("conference_list"))
        assert reverse("start_new_year") in response.content.decode()

    def test_list_hides_start_button_once_the_next_exists(
        self, client, admin_user, conference
    ):
        Conference.objects.create(
            year=conference.year + 1, name="Next", slug="next-edition"
        )
        client.force_login(admin_user)
        response = client.get(reverse("conference_list"))
        assert reverse("start_new_year") not in response.content.decode()

    def test_update_conference(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": "Renamed Edition",
                "slug": conference.slug,
                "cadence": "ONCE",
                "sponsorship_goal": "15000",
                "donation_goal": "2500",
                "proposals_count": "0",
                "chat_platform": "DISCORD",
                "conference_date": "2025-11-15",
            },
            follow=True,
        )
        assert response.status_code == 200
        conference.refresh_from_db()
        assert conference.name == "Renamed Edition"
        assert str(conference.conference_date) == "2025-11-15"

    def test_switching_the_module_on_seeds_the_checklists(
        self, client, admin_user, conference
    ):
        """The edition gets its defaults, on the format just chosen, the
        moment the speaker module is switched on; switching it off and on
        again leaves what organizers have."""
        SpeakerSettings.objects.filter(conference=conference).delete()
        client.force_login(admin_user)
        data = {
            "year": conference.year,
            "name": conference.name,
            "slug": conference.slug,
            "cadence": "ONCE",
            "conference_date": "2027-05-01",
            "sponsorship_goal": "0",
            "donation_goal": "0",
            "proposals_count": "0",
            "chat_platform": "NONE",
            "speaker_module_enabled": "on",
            "event_format": EventFormat.IN_PERSON,
            "recordings": Recordings.TEAM,
        }
        url = reverse("conference_edit", kwargs={"pk": conference.pk})
        client.post(url, data)
        templates = ChecklistTemplate.objects.filter(conference=conference)
        assert templates.filter(name="Recorded session").exists()
        assert not templates.filter(name="Performer").exists()
        count = templates.count()
        client.post(url, data)
        assert templates.count() == count
        assert seed_new_edition(conference) is None

    def test_update_saves_venue_and_format(self, client, admin_user, conference):
        # The format is chosen on the edition form and kept on
        # the speaker settings row, created here when there is none.
        SpeakerSettings.objects.filter(conference=conference).delete()
        venue = Venue.objects.create(name="Long Beach Convention Center")
        client.force_login(admin_user)
        client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": conference.name,
                "slug": conference.slug,
                "cadence": "ONCE",
                "sponsorship_goal": "0",
                "donation_goal": "0",
                "proposals_count": "0",
                "chat_platform": "DISCORD",
                "conference_date": "2026-05-16",
                "venue": venue.pk,
                "event_format": EventFormat.IN_PERSON,
                "recordings": Recordings.TEAM,
            },
            follow=True,
        )
        conference.refresh_from_db()
        assert conference.venue == venue
        row = SpeakerSettings.objects.get(conference=conference)
        assert row.event_format == EventFormat.IN_PERSON
        assert row.recordings == Recordings.TEAM
        assert row.speaker_module_enabled is False
        # The form shows what is stored, and a second save changes only the
        # format on the existing row.
        content = client.get(
            reverse("conference_edit", kwargs={"pk": conference.pk})
        ).content.decode()
        assert 'value="IN_PERSON" selected' in content
        client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": conference.name,
                "slug": conference.slug,
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "sponsorship_goal": "0",
                "donation_goal": "0",
                "proposals_count": "0",
                "chat_platform": "DISCORD",
                "event_format": EventFormat.HYBRID,
                "recordings": Recordings.SPEAKERS,
            },
        )
        row.refresh_from_db()
        assert row.event_format == EventFormat.HYBRID
        assert row.recordings == Recordings.SPEAKERS

    def test_in_person_speakers_cannot_pre_record(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": conference.name,
                "slug": conference.slug,
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "sponsorship_goal": "0",
                "donation_goal": "0",
                "proposals_count": "0",
                "chat_platform": "DISCORD",
                "event_format": EventFormat.IN_PERSON,
                "recordings": Recordings.SPEAKERS,
            },
        )
        assert response.status_code == 200
        assert "Speakers do not pre-record" in response.content.decode()

    def test_update_without_a_format_makes_no_settings_row(
        self, client, admin_user, conference
    ):
        # The default format and the module off: nothing worth a row.
        SpeakerSettings.objects.filter(conference=conference).delete()
        client.force_login(admin_user)
        client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": conference.name,
                "slug": conference.slug,
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "sponsorship_goal": "0",
                "donation_goal": "0",
                "proposals_count": "0",
                "chat_platform": "DISCORD",
            },
        )
        assert not SpeakerSettings.objects.filter(conference=conference).exists()

    def test_delete_empty_conference(self, client, admin_user, conference):
        extra = Conference.objects.create(year=2099, name="Empty", slug="empty")
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_delete", kwargs={"pk": extra.pk}), follow=True
        )
        assert response.status_code == 200
        assert not Conference.objects.filter(pk=extra.pk).exists()

    def test_delete_blocked_when_has_data(self, client, admin_user, conference):
        extra = Conference.objects.create(year=2099, name="HasData", slug="hasdata")
        Team.objects.create(conference=extra, short_name="T", description="d")
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_delete", kwargs={"pk": extra.pk}), follow=True
        )
        assert response.status_code == 200
        assert Conference.objects.filter(pk=extra.pk).exists()  # protected, not deleted
        assert "Cannot delete" in response.content.decode()

    def test_requires_superuser(self, client, django_user_model, conference):
        staff = django_user_model.objects.create_user("staffy2", is_staff=True)
        client.force_login(staff)
        urls = [
            reverse("conference_list"),
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            reverse("conference_delete", kwargs={"pk": conference.pk}),
        ]
        for url in urls:
            assert client.get(url).status_code in (302, 403)


@pytest.mark.django_db
class TestOrganizerDashboard:
    def test_requires_admin(self, client, portal_user):
        client.force_login(portal_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.status_code in (302, 403)

    def test_renders_for_admin(self, client, admin_user, conference):
        conference.sponsors_url = "https://2025.example.org/sponsors/"
        conference.save()
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Organizer dashboard" in content
        assert response.context["conference"] == conference
        # Quick actions include managing the sponsor list, not just adding one.
        assert "Manage sponsors" in content
        assert reverse("sponsorship:sponsorship_list") in content
        # Contextual sponsorship resources below Quick actions, not the footer.
        assert "Sponsorship resources" in content
        assert "Sponsorship prospectus" in content
        # The footer resources stay on the logged-out landing only.
        assert "footer-heading" not in content
        assert "Portal documentation" not in content

    def test_rail_follows_the_organizers_sets(
        self, client, django_user_model, conference, organizer, grant_organizer
    ):
        """A member manages conferences but does not start the year; a lead
        does both; a staff account on no team sees no organizer surface."""
        client.force_login(organizer)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert reverse("conference_list") in content
        assert reverse("start_new_year") not in content
        assert client.get(reverse("conference_list")).status_code == 200
        assert client.get(reverse("start_new_year")).status_code == 403
        grant_organizer(organizer, lead=True)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert reverse("start_new_year") in content
        assert client.get(reverse("start_new_year")).status_code == 200
        staff = django_user_model.objects.create_user("staff", is_staff=True)
        client.force_login(staff)
        assert client.get(reverse("organizer_dashboard")).status_code == 403
        assert client.get(reverse("conference_list")).status_code == 403

    def test_no_active_edition_notice(self, client, organizer, admin_user, conference):
        """Team grants belong to the active edition, so with none active an
        organizer holds nothing and the dashboard refuses them; the notice
        that says to ask a superuser is, fittingly, the superuser's."""
        conference.is_active = False
        conference.save()
        client.force_login(organizer)
        assert client.get(reverse("organizer_dashboard")).status_code == 403
        client.force_login(admin_user)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert "No active event." in content
        assert reverse("conference_list") in content

    def test_needs_attention_counts(
        self, client, admin_user, conference, django_user_model
    ):
        # An unled team with a pending member.
        team = Team.objects.create(
            short_name="Comms", description="d", conference=conference
        )
        member = VolunteerProfile.objects.create(
            user=django_user_model.objects.create_user("m1"),
            conference=conference,
            application_status=ApplicationStatus.PENDING,
        )
        member.teams.add(team)
        # A committed-but-uninvoiced sponsor.
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=1000, description="g", conference=conference
        )
        SponsorshipProfile.objects.create(
            organization_name="Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.context["pending_reviews"] == 1
        assert response.context["unled_teams"] == 1
        assert response.context["awaiting_invoice"] == 1

    def test_cancelled_volunteers_excluded_from_pending_reviews(
        self, client, admin_user, conference, django_user_model
    ):
        team = Team.objects.create(
            short_name="Comms", description="d", conference=conference
        )
        pending = VolunteerProfile.objects.create(
            user=django_user_model.objects.create_user("p1"),
            conference=conference,
            application_status=ApplicationStatus.PENDING,
        )
        pending.teams.add(team)
        # A cancelled volunteer, even if still linked to the team, must not be
        # counted as needing review.
        cancelled = VolunteerProfile.objects.create(
            user=django_user_model.objects.create_user("c1"),
            conference=conference,
            application_status=ApplicationStatus.CANCELLED,
        )
        cancelled.teams.add(team)
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.context["pending_reviews"] == 1  # only the pending one

    def test_pending_volunteer_without_a_team_is_counted(
        self, client, admin_user, conference, django_user_model
    ):
        # A volunteer who applied without picking a team still needs review;
        # it is only reachable from the volunteers list (no team lists it).
        VolunteerProfile.objects.create(
            user=django_user_model.objects.create_user("noteam"),
            conference=conference,
            application_status=ApplicationStatus.PENDING,
        )
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.context["pending_reviews"] == 1
        # The alert points at the volunteers list, filtered to pending, so the
        # organizer can find team-less applicants.
        content = response.content.decode()
        assert reverse("volunteer:volunteers_list") in content
        assert "application_status=Pending%20Review" in content

    def test_pending_across_multiple_teams_counts_the_volunteer_once(
        self, client, admin_user, conference, django_user_model
    ):
        a = Team.objects.create(short_name="A", description="d", conference=conference)
        b = Team.objects.create(short_name="B", description="d", conference=conference)
        applicant = VolunteerProfile.objects.create(
            user=django_user_model.objects.create_user("multi"),
            conference=conference,
            application_status=ApplicationStatus.PENDING,
        )
        applicant.teams.add(a, b)
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.context["pending_reviews"] == 1  # one volunteer, not two

    def test_no_active_conference_renders_zeros(self, client, admin_user, conference):
        conference.is_active = False
        conference.save()
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        assert response.status_code == 200
        assert response.context["conference"] is None
        assert response.context["pending_reviews"] == 0
        assert response.context["unled_teams"] == 0
        assert response.context["awaiting_invoice"] == 0

    def test_no_active_conference_flagged_in_needs_attention(
        self, client, admin_user, conference
    ):
        conference.is_active = False
        conference.save()
        client.force_login(admin_user)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert "No active event." in content
        assert reverse("conference_list") in content
        # It is an attention item, not the "nothing to do" state.
        assert "Nothing needs your attention" not in content

    def test_goal_percent_rounded_and_bar_capped(self, client, admin_user, conference):
        # A paid sponsor that beats the goal -> percent > 100 with a long decimal.
        tier = SponsorshipTier.objects.create(
            name="Big", amount=50000, description="d", conference=conference
        )
        SponsorshipProfile.objects.create(
            organization_name="Whale",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.PAID,
            conference=conference,
        )
        client.force_login(admin_user)
        response = client.get(reverse("organizer_dashboard"))
        pct = response.context["sponsorship_goal_percent"]
        assert pct > 100  # goal exceeded
        assert pct == int(pct)  # rounded, not a long decimal
        assert response.context["sponsorship_bar_width"] == 100  # bar capped


@pytest.mark.django_db
class TestConferenceBanner:
    def test_banner_shown_when_set(self, client, conference):
        conference.banner_text = "Call for proposals is open!"
        conference.save()
        content = client.get(reverse("portal_stats")).content.decode()
        assert 'id="conference-banner"' in content
        assert "alert-beam" in content  # the event-wide announcement tone
        assert "Call for proposals is open!" in content

    def test_no_banner_when_empty(self, client, conference):
        content = client.get(reverse("portal_stats")).content.decode()
        assert 'id="conference-banner"' not in content


@pytest.mark.django_db
class TestBranding:
    def test_brand_assets_loaded(self, client, conference):
        content = client.get(reverse("portal_stats")).content.decode()
        # The instance theme stylesheet and the generated favicon, both
        # versioned by the brand's content hash.
        version = settings.BRAND.version
        assert f'{reverse("brand_theme_css")}?v={version}' in content
        assert f'{reverse("brand_favicon")}?v={version}' in content
        assert settings.BRAND.short_name in content


@pytest.mark.django_db
class TestConferenceUrls:
    def test_form_saves_custom_urls(self, client, admin_user, conference):
        client.force_login(admin_user)
        client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            {
                "year": conference.year,
                "name": conference.name,
                "slug": conference.slug,
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "sponsorship_goal": "15000",
                "donation_goal": "2500",
                "proposals_count": "0",
                "chat_platform": "DISCORD",
                "sponsors_url": "https://2026.example.com/sponsors/",
                "donate_url": "https://2026.example.com/donate/",
            },
            follow=True,
        )
        conference.refresh_from_db()
        assert conference.sponsors_url == "https://2026.example.com/sponsors/"

    def test_template_uses_custom_url_when_set(self, client, conference):
        conference.sponsors_url = "https://2026.example.com/sponsors/"
        conference.save()
        content = client.get(reverse("portal_stats")).content.decode()
        assert "https://2026.example.com/sponsors/" in content

    def test_no_sponsor_callout_without_a_url(self, client, conference):
        # No prospectus and no donation page: the callout stays off the page
        # rather than pointing at a placeholder.
        content = client.get(reverse("portal_stats")).content.decode()
        assert "Sponsorship prospectus" not in content
        assert "Sponsor us" not in content
