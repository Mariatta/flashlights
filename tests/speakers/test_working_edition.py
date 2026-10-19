"""Planning a newer edition while the active one runs: the organizer's
working edition, and speakers taken to the edition they speak at."""

from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory
from django.urls import reverse

from portal.models import Conference
from speakers.checklists import add_adhoc_item
from speakers.constants import ItemOwner, ItemStatus
from speakers.context_processors import speaker_module
from speakers.editions import (
    SESSION_KEY,
    active_edition,
    module_enabled,
    program_editions,
    queue_editions,
    set_working_edition,
    speaker_edition,
    working_edition,
)
from speakers.emails import signed_invitation_token
from speakers.models import ChecklistItem
from speakers.onboarding import welcome_url_for
from speakers.services import invitation_edition, send_invitation
from tests.grants import on_team
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_proposal,
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

    def test_tasks_come_from_the_editions_on_offer(self, conference, enabled):
        assert queue_editions(request_with({})) == [conference]
        enabled.speaker_module_enabled = False
        enabled.save()
        assert queue_editions(request_with({})) == []

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

    def test_the_rooms_tab_is_on_the_edition_the_program_pages_show(
        self, client, admin_user, conference, upcoming
    ):
        rooms = f'href="{reverse("speakers:room_list")}">Rooms</a>'

        def edit_page(edition):
            url = reverse("conference_edit", kwargs={"pk": edition.pk})
            return client.get(url).content.decode()

        client.force_login(admin_user)
        assert rooms in edit_page(conference) and rooms not in edit_page(upcoming)
        switch(client, upcoming)
        assert rooms not in edit_page(conference) and rooms in edit_page(upcoming)

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
        # Whether the call is open, and whether "My proposals" shows, read
        # the active edition while the next one is being planned.
        upcoming.speaker_settings.proposals_open = True
        upcoming.speaker_settings.save()

        def flags_now():
            fresh = request_with(client.session)
            fresh.user = organizer
            return speaker_module(fresh)

        assert flags_now()["speaker_proposals_open"] is False
        assert flags_now()["has_speaker_proposals"] is False
        make_proposal(make_session(upcoming), make_presenter(upcoming, user=organizer))
        assert flags_now()["has_speaker_proposals"] is False
        make_proposal(
            make_session(conference), make_presenter(conference, user=organizer)
        )
        assert flags_now()["has_speaker_proposals"] is True
        upcoming.speaker_settings.proposals_open = False
        upcoming.speaker_settings.save()
        conference.speaker_settings.proposals_open = True
        conference.speaker_settings.save()
        assert flags_now()["speaker_proposals_open"] is True

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


QUEUE = reverse("speakers:checklist_queue")


def task_for(edition, title, **owner):
    """An organizer item for a presenter of ``edition``."""
    presenter = make_presenter(edition, display_name=f"Speaker of {title}")
    add_presenter(make_session(edition), presenter, confirmed=True)
    return add_adhoc_item(
        edition, title, ItemOwner.ORGANIZER, presenter=presenter, **owner
    )


@pytest.mark.django_db
class TestVolunteeringTasksAcrossEditions:
    """My volunteering tasks lists the active edition's tasks and any newer
    edition's, whichever one the program pages are planning."""

    def test_planning_the_next_edition_hides_nothing(
        self, client, organizer, conference, upcoming
    ):
        task_for(conference, "Promo for this year", assignee=organizer)
        task_for(upcoming, "Promo for next year", assignee=organizer)
        client.force_login(organizer)
        for chosen in (conference, upcoming):
            switch(client, chosen)
            page = client.get(QUEUE).content.decode()
            assert "Promo for this year" in page and "Promo for next year" in page
            # Only the task of the edition that is not the active one says so.
            assert page.count(">Flashlights 2026</span>") == 1
            assert ">Flashlights 2025</span>" not in page

    def test_a_task_is_ticked_in_its_own_edition(
        self, client, organizer, conference, upcoming
    ):
        task = task_for(conference, "Promo for this year", assignee=organizer)
        client.force_login(organizer)
        switch(client, upcoming)
        url = reverse("speakers:item_status", args=[task.pk])
        response = client.post(
            url, {"status": ItemStatus.DONE, "partial": "queue"}, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 200
        task.refresh_from_db()
        assert task.status == ItemStatus.DONE
        detail = client.get(reverse("speakers:item_detail", args=[task.pk]))
        assert detail.status_code == 200
        # An edition before the active one is not on the list.
        past = Conference.objects.create(year=2024, name="Past", slug="2024")
        make_settings(past)
        old = task_for(past, "Last year's", assignee=organizer)
        assert (
            client.post(
                reverse("speakers:item_status", args=[old.pk]), {"status": "DONE"}
            ).status_code
            == 404
        )

    def test_another_editions_presenter_is_named_without_a_link(
        self, client, organizer, conference, upcoming
    ):
        task = task_for(upcoming, "Promo for next year", assignee=organizer)
        presenter_page = task.presenter.get_absolute_url()
        client.force_login(organizer)
        # Working on this year: next year's presenter page would not open.
        page = client.get(QUEUE, {"view": "presenter"}).content.decode()
        assert task.presenter.display_name in page
        assert presenter_page not in page
        detail = client.get(reverse("speakers:item_detail", args=[task.pk]))
        html = detail.content.decode()
        assert ">Flashlights 2026</span>" in html and presenter_page not in html
        response = client.post(
            reverse("speakers:item_status", args=[task.pk]), {"status": "DONE"}
        )
        assert response.url == QUEUE
        # Planning next year: its presenter is linked again.
        switch(client, upcoming)
        response = client.post(
            reverse("speakers:item_status", args=[task.pk]), {"status": "TODO"}
        )
        assert response.url == presenter_page
        page = client.get(QUEUE, {"view": "presenter"}).content.decode()
        assert presenter_page in page
        html = client.get(reverse("speakers:item_detail", args=[task.pk]))
        assert presenter_page in html.content.decode()

    def test_a_team_task_counts_the_teams_of_its_own_edition(
        self, client, conference, upcoming
    ):
        ada = User.objects.create_user(username="ada", email="ada@x.org")
        next_team = Team.objects.create(
            conference=upcoming, short_name="Promo 2026", description="d"
        )
        this_team = Team.objects.create(
            conference=conference, short_name="Promo 2025", description="d"
        )
        task_for(upcoming, "Next year team task", team=next_team)
        task_for(conference, "This year team task", team=this_team)
        # Ada is on next year's team only; this year she is not on the team.
        profile = VolunteerProfile.objects.create(
            user=ada,
            conference=upcoming,
            application_status=ApplicationStatus.APPROVED,
        )
        profile.teams.add(next_team)
        client.force_login(ada)
        # Her only task is next year's, and that opens the page.
        page = client.get(QUEUE).content.decode()
        assert "Next year team task" in page
        assert "This year team task" not in page
        assert ChecklistItem.objects.count() == 2
