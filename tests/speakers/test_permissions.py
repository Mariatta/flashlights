"""Speakers on has_perm (design §7.1, task 3.4): a Program-team member runs
the program with no Django flag, a Recordings-team member reads it and cannot
invite, and liaison scoping is untouched (the existing suites cover it)."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.constants import SessionStatus

from .factories import make_presenter, make_proposal, make_session, make_settings

SESSIONS = reverse("speakers:session_list")
NEW_SESSION = reverse("speakers:session_create")
PRESENTERS = reverse("speakers:presenter_list")
NEW_PRESENTER = reverse("speakers:presenter_create")
QUEUE = reverse("speakers:proposal_queue")
TEMPLATES = reverse("speakers:template_list")
HANDBOOK = reverse("speakers:handbook_list")
TYPES = reverse("speakers:program_types")
GATES = reverse("speakers:readiness_gates")
BOARD = reverse("speakers:checklist_board")


@pytest.fixture
def enabled(conference):
    return make_settings(conference, proposals_open=True)


@pytest.fixture
def programmer(join_team):
    return join_team(
        User.objects.create_user(username="pat", email="pat@x.org"), "Program"
    )


@pytest.fixture
def designer(join_team):
    return join_team(
        User.objects.create_user(username="dee", email="dee@x.org"), "Recordings"
    )


@pytest.mark.django_db
class TestProgramTeamMember:
    def test_runs_the_program_with_no_flag(
        self, client, programmer, conference, enabled
    ):
        assert not programmer.is_staff and not programmer.is_superuser
        client.force_login(programmer)
        for url in (SESSIONS, NEW_SESSION, PRESENTERS, NEW_PRESENTER, QUEUE, BOARD):
            assert client.get(url).status_code == 200, url
        # Creating a session and inviting from its page.
        response = client.post(
            NEW_SESSION,
            {"kind": conference.session_types.get(code="TALK").pk, "title": "Perms"},
        )
        assert response.status_code == 302
        session = conference.sessions.get(title="Perms")
        page = client.get(session.get_absolute_url()).content.decode()
        assert "New presenter" in page
        # Deciding a proposal.
        presenter = make_presenter(conference)
        proposed = make_session(conference, title="Idea", status=SessionStatus.PROPOSED)
        proposal = make_proposal(proposed, presenter)
        decide = reverse("speakers:proposal_decide", args=[proposal.pk])
        assert client.post(decide, {"decision": "REJECTED"}).status_code == 302
        # Templates and guides are content work the Program set carries.
        assert client.get(TEMPLATES).status_code == 200
        assert client.get(HANDBOOK).status_code == 200

    def test_settings_are_the_leads(self, client, programmer, join_team, enabled):
        client.force_login(programmer)
        assert client.get(TYPES).status_code == 403
        assert client.get(GATES).status_code == 403
        join_team(programmer, "Program", lead=True)
        assert client.get(TYPES).status_code == 200
        assert client.get(GATES).status_code == 200

    def test_rail_offers_what_the_person_holds(
        self, client, programmer, organizer, join_team, enabled
    ):
        client.force_login(organizer)
        content = client.get(SESSIONS).content.decode()
        assert TYPES in content and TEMPLATES in content and HANDBOOK in content
        client.force_login(programmer)
        content = client.get(SESSIONS).content.decode()
        assert TYPES not in content and GATES not in content
        assert TEMPLATES in content and HANDBOOK in content


@pytest.mark.django_db
class TestSpeakerLiaisonsMember:
    def test_sees_their_tasks_page_before_any_assignment(
        self, client, join_team, enabled
    ):
        lena = join_team(User.objects.create_user(username="lena"), "Speaker liaisons")
        client.force_login(lena)
        queue = reverse("speakers:checklist_queue")
        assert client.get(queue).status_code == 200
        assert queue in client.get(reverse("volunteer:index")).content.decode()
        # Reading the program is still not theirs.
        assert client.get(SESSIONS).status_code == 403


@pytest.mark.django_db
class TestRecordingsTeamMember:
    def test_reads_but_cannot_invite(self, client, designer, conference, enabled):
        session = make_session(conference, title="Read me")
        client.force_login(designer)
        assert client.get(SESSIONS).status_code == 200
        assert client.get(PRESENTERS).status_code == 200
        page = client.get(session.get_absolute_url())
        assert page.status_code == 200
        assert "New presenter" not in page.content.decode()
        for url in (NEW_SESSION, NEW_PRESENTER, TEMPLATES, HANDBOOK, TYPES):
            assert client.get(url).status_code == 403, url
        assert client.post(NEW_SESSION, {"title": "No"}).status_code == 403

    def test_staff_flag_alone_opens_nothing(self, client, conference, enabled):
        staff = User.objects.create_user(username="staffy", is_staff=True)
        client.force_login(staff)
        assert client.get(SESSIONS).status_code == 403
        assert client.get(NEW_SESSION).status_code == 403
