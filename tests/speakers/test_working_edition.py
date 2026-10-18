"""Planning a newer edition while the active one runs: the organizer's
working edition, and speakers taken to the edition they speak at."""

from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory
from django.urls import reverse

from portal.models import Conference
from speakers.context_processors import speaker_module
from speakers.editions import (
    SESSION_KEY,
    active_edition,
    module_enabled,
    program_editions,
    set_working_edition,
    speaker_edition,
    working_edition,
)
from speakers.emails import signed_invitation_token
from speakers.onboarding import welcome_url_for
from speakers.services import invitation_edition, send_invitation
from tests.grants import on_team

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_session,
    make_settings,
)

SWITCH = reverse("speakers:working_edition")


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def upcoming(db, enabled):
    """The next edition, planned while the fixture's 2025 one is active."""
    edition = Conference.objects.create(year=2026, name="Flashlights 2026", slug="2026")
    make_settings(edition)
    return edition


@pytest.fixture
def organizer(db):
    return on_team(User.objects.create_user(username="org", email="org@x.org"))


def request_with(session):
    """A new request, as each page load is: what one request read about
    the editions is not read again."""
    request = RequestFactory().get("/")
    request.session = session
    return request


def speaker_on(edition, username="ada"):
    user, _ = User.objects.get_or_create(
        username=username, defaults={"email": f"{username}@x.org"}
    )
    presenter = make_presenter(edition, user=user)
    add_presenter(make_session(edition), presenter, confirmed=True)
    return user


def switch(client, edition, **extra):
    return client.post(SWITCH, {"edition": edition.pk, **extra})


@pytest.mark.django_db
class TestEditions:
    def test_the_active_and_newer_ones_with_the_portal_on(self, conference, upcoming):
        Conference.objects.create(year=2024, name="Past", slug="2024")
        Conference.objects.create(year=2027, name="Off", slug="2027")
        assert program_editions() == [conference, upcoming]
        conference.is_active = False
        conference.save()
        assert program_editions() == []
        assert working_edition(request_with({})) is None

    def test_a_choice_no_longer_offered_falls_back(self, conference, upcoming):
        assert working_edition(request_with({})) == conference
        chosen = {SESSION_KEY: upcoming.pk}
        assert working_edition(request_with(chosen)) == upcoming
        upcoming.speaker_settings.speaker_module_enabled = False
        upcoming.speaker_settings.save()
        assert working_edition(request_with(chosen)) == conference

    def test_an_active_edition_without_a_program_hands_over_to_the_next(
        self, client, organizer, conference, upcoming
    ):
        conference.speaker_settings.speaker_module_enabled = False
        conference.speaker_settings.save()
        assert program_editions() == [upcoming]
        chosen = {SESSION_KEY: conference.pk}
        assert working_edition(request_with(chosen)) == upcoming
        upcoming.speaker_settings.speaker_module_enabled = False
        upcoming.speaker_settings.save()
        assert working_edition(request_with(chosen)) == conference
        upcoming.speaker_settings.speaker_module_enabled = True
        upcoming.speaker_settings.save()
        make_session(upcoming, title="Planned talk")
        client.force_login(organizer)
        page = client.get(reverse("speakers:session_list")).content.decode()
        assert "Planned talk" in page and "You are planning" in page


@pytest.mark.django_db
class TestOncePerRequest:
    def test_the_rails_the_switcher_and_the_view_share_one_read(
        self, organizer, conference, upcoming, django_assert_num_queries
    ):
        request = request_with({SESSION_KEY: upcoming.pk})
        request.user = organizer
        speaker_module(request)
        with django_assert_num_queries(0):
            assert active_edition(request) == conference
            assert working_edition(request) == upcoming
            assert program_editions(request) == [conference, upcoming]
            assert module_enabled(upcoming, request)
        # Switching forgets the working edition, and only that: the one
        # read left is whether the active edition's portal is on.
        set_working_edition(request, conference)
        with django_assert_num_queries(1):
            assert working_edition(request) == conference


@pytest.mark.django_db
class TestSwitching:
    def test_organizer_pages_follow_the_working_edition(
        self, client, organizer, conference, upcoming
    ):
        make_session(conference, title="Current talk")
        make_session(upcoming, title="Planned talk")
        upcoming.event_dates.create(date=date(2026, 2, 13))
        client.force_login(organizer)
        page = client.get(reverse("speakers:session_list")).content.decode()
        assert "Current talk" in page and "Planned talk" not in page
        assert "Program for" in page
        assert "You are planning" not in page
        response = switch(client, upcoming, next=reverse("speakers:schedule_editor"))
        assert response.url == reverse("speakers:schedule_editor")
        page = client.get(reverse("speakers:session_list")).content.decode()
        assert "Planned talk" in page and "Current talk" not in page
        assert (
            "You are planning Flashlights 2026. The public site still shows "
            "Flashlights 2025." in page
        )
        editor = client.get(reverse("speakers:schedule_editor"))
        assert editor.context["days"] == [date(2026, 2, 13)]
        # Back to the active one, from a page whose address is not ours.
        response = switch(client, conference, next="https://elsewhere.example/")
        assert response.url == reverse("speakers:session_list")
        assert client.session[SESSION_KEY] == conference.pk

    def test_switching_from_one_sessions_page_lands_on_the_sessions(
        self, client, organizer, conference, upcoming
    ):
        session = make_session(conference, title="Current talk")
        client.force_login(organizer)
        detail = reverse("speakers:session_detail", args=[session.slug])
        assert client.get(detail).status_code == 200
        response = switch(client, upcoming, next=detail + "?tab=files")
        assert response.url == reverse("speakers:session_list")
        assert client.get(response.url).status_code == 200
        response = switch(client, conference, next="/no/such/page/")
        assert response.url == reverse("speakers:session_list")

    def test_only_offered_editions_and_only_to_program_staff(
        self, client, organizer, conference, upcoming
    ):
        past = Conference.objects.create(year=2024, name="Past", slug="2024")
        make_settings(past)
        client.force_login(organizer)
        assert switch(client, past).status_code == 404
        assert client.post(SWITCH, {"edition": "x"}).status_code == 404
        client.force_login(User.objects.create_user(username="someone"))
        assert switch(client, upcoming).status_code == 404

    def test_no_switcher_with_a_single_edition(self, client, organizer, enabled):
        client.force_login(organizer)
        page = client.get(reverse("speakers:session_list")).content.decode()
        assert "Program for" not in page

    def test_the_public_call_stays_on_the_active_edition(
        self, client, organizer, conference, upcoming
    ):
        client.force_login(organizer)
        switch(client, upcoming)
        response = client.get(reverse("speakers:propose"))
        assert response.context["view"].conference == conference
        request = RequestFactory().get("/")
        request.user = organizer
        request.session = client.session
        flags = speaker_module(request)
        assert flags["speaker_module_enabled"] is True

    def test_starting_the_next_edition_plans_it(self, client, admin_user, enabled):
        client.force_login(admin_user)
        client.post(
            reverse("start_new_year"),
            {
                "year": 2026,
                "name": "Flashlights 2026",
                "slug": "2026",
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "speaker_portal": "on",
            },
        )
        upcoming = Conference.objects.get(year=2026)
        assert not upcoming.is_active
        assert client.session[SESSION_KEY] == upcoming.pk


@pytest.mark.django_db
class TestSpeakers:
    def test_a_speaker_of_the_next_edition_has_their_pages(
        self, client, conference, upcoming
    ):
        user = speaker_on(upcoming)
        assert speaker_edition(user) == upcoming
        assert welcome_url_for(user) == reverse("speakers:my_welcome")
        client.force_login(user)
        assert client.get(reverse("speakers:index")).url == reverse(
            "speakers:my_dashboard"
        )
        dashboard = client.get(reverse("speakers:my_dashboard"))
        assert dashboard.status_code == 200
        assert dashboard.context["view"].conference == upcoming
        assert dashboard.context["is_speaker_presenter"] is True

    def test_the_active_edition_first_unless_preferred(self, conference, upcoming):
        user = speaker_on(conference)
        speaker_on(upcoming, user.username)
        assert speaker_edition(user) == conference
        assert speaker_edition(user, upcoming) == upcoming

    def test_nobody_on_the_program(self, conference, upcoming):
        assert speaker_edition(AnonymousUser()) is None
        user = User.objects.create_user(username="visitor")
        assert speaker_edition(user) is None
        assert welcome_url_for(user) is None

    def test_an_invitation_opens_in_its_own_edition(
        self, client, admin_user, conference, upcoming
    ):
        session = make_session(upcoming, title="February workshop")
        presenter = make_presenter(upcoming, email="ada@example.com")
        add_presenter(session, presenter)
        invitation = make_invitation(presenter, session)
        send_invitation(invitation, actor=admin_user)
        invitation.refresh_from_db()
        token = signed_invitation_token(invitation)
        assert invitation_edition(token) == upcoming
        response = client.get(reverse("speakers:invitation", args=[token]))
        assert [t.name for t in response.templates][0] == "speakers/invitation.html"
        assert response.context["conference"] == upcoming
        assert invitation_edition("nope") is None

    def test_an_older_editions_invitation_is_not_resolved(self, conference, enabled):
        past = Conference.objects.create(year=2024, name="Past", slug="2024")
        make_settings(past)
        presenter = make_presenter(past)
        invitation = make_invitation(presenter, make_session(past))
        assert invitation_edition(signed_invitation_token(invitation)) is None
