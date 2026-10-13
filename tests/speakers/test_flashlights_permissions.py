"""The permissions Flashlights adds to the ported catalogue: reviewers
answer proposals without running the program, publishing has its own
permission, a Recordings team runs the media pipeline, the video fields
need publish_session_video, and ticketing has two of its own."""

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from speakers.constants import MediaKind, ProposalDecision, SessionStatus
from speakers.forms import SessionForm
from speakers.media import can_delete, can_download, can_upload
from speakers.models import MediaAsset
from tests.grants import on_team
from volunteer.models import Team, VolunteerProfile

from .factories import (
    add_presenter,
    make_presenter,
    make_proposal,
    make_session,
    make_settings,
)


@pytest.fixture
def enabled(conference):
    return make_settings(conference, proposals_open=True)


def account(name, team):
    return on_team(User.objects.create_user(username=name, email=f"{name}@x.org"), team)


def holding(name, *codenames):
    """An approved member of a team granting exactly ``codenames``."""
    user = account(name, "Speaker liaisons")
    team = Team.objects.create(
        conference=Team.objects.get(short_name="Speaker liaisons").conference,
        short_name=f"Only {name}",
        description="d",
    )
    team.permissions.set(Permission.objects.filter(codename__in=codenames))
    VolunteerProfile.objects.get(user=user).teams.add(team)
    return user


@pytest.mark.django_db
class TestProposalReviewers:
    def test_answer_proposals_without_running_the_program(
        self, client, conference, enabled
    ):
        reviewer = account("rae", "Proposal reviewers")
        session = make_session(conference, status=SessionStatus.PROPOSED)
        presenter = make_presenter(conference)
        add_presenter(session, presenter)
        proposal = make_proposal(session, presenter)
        client.force_login(reviewer)
        queue = client.get(reverse("speakers:proposal_queue"))
        assert queue.status_code == 200 and queue.context["can_decide"]
        client.post(
            reverse("speakers:proposal_decide", args=[proposal.pk]),
            {"decision": ProposalDecision.APPROVED},
        )
        proposal.refresh_from_db()
        assert proposal.decision == ProposalDecision.APPROVED
        assert client.get(reverse("speakers:session_create")).status_code == 403
        assert client.get(reverse("speakers:program_publishing")).status_code == 403

    def test_a_program_reader_reads_the_queue_but_cannot_decide(
        self, client, conference, enabled
    ):
        reader = holding("rey", "view_program")
        client.force_login(reader)
        queue = client.get(reverse("speakers:proposal_queue"))
        assert queue.status_code == 200 and not queue.context["can_decide"]


@pytest.mark.django_db
class TestPublishing:
    def test_publishing_reads_its_own_permission(self, client, conference, enabled):
        client.force_login(holding("pia", "publish_program"))
        assert client.get(reverse("speakers:program_publishing")).status_code == 200
        client.force_login(holding("pat", "view_program", "manage_program"))
        assert client.get(reverse("speakers:program_publishing")).status_code == 403


@pytest.mark.django_db
class TestRecordingsTeam:
    def test_runs_the_media_pipeline_without_the_program(self, conference, enabled):
        rec = account("ren", "Recordings")
        lead = on_team(
            User.objects.create_user(username="lin", email="lin@x.org"),
            "Recordings",
            lead=True,
        )
        session = make_session(conference)
        asset = MediaAsset.objects.create(
            session=session,
            kind=MediaKind.PROCESSED_VIDEO,
            conference=conference,
            original_filename="cut.mp4",
        )
        assert can_upload(rec, session, MediaKind.PROCESSED_VIDEO)
        assert can_download(rec, session, asset)
        assert not can_delete(rec, session, asset)
        assert can_delete(lead, session, asset)
        assert not rec.has_perm("speakers.manage_program")

    def test_the_video_fields_need_publish_session_video(self, conference, enabled):
        with_video = account("vic", "Recordings")
        without = holding("val", "manage_program", "view_program")
        assert (
            "youtube_url" in SessionForm(conference=conference, user=with_video).fields
        )
        fields = SessionForm(conference=conference, user=without).fields
        assert "youtube_url" not in fields and "premiere_location" not in fields


@pytest.mark.django_db
class TestTicketing:
    def test_settings_and_import_have_their_own_permissions(self, client, conference):
        settings_url = reverse("conference_tickets", args=[conference.pk])
        import_url = reverse("conference_tickets_import", args=[conference.pk])
        desk = holding("dee", "import_registrations")
        client.force_login(desk)
        assert client.get(settings_url).status_code == 403
        assert client.get(import_url).status_code in (200, 302)
        rail = client.get(reverse("organizer_dashboard"))
        assert rail.status_code == 403  # no dashboard: the import is all they hold
        client.force_login(account("ora", "Organizers"))
        assert client.get(settings_url).status_code == 200
        client.force_login(holding("nil"))
        assert client.get(import_url).status_code == 403
