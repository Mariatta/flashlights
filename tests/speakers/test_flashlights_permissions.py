"""The permissions Flashlights adds to the ported catalogue: reviewers
answer proposals without running the program, publishing has its own
permission, a Recordings team runs the media pipeline, the video fields
need publish_session_video, and ticketing has two of its own."""

from datetime import datetime, timezone

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.urls import reverse

from speakers.constants import (
    Delivery,
    EventFormat,
    ItemOwner,
    MediaKind,
    PremiereLocation,
    ProposalDecision,
    Recordings,
    SessionStatus,
)
from speakers.forms import SessionForm, SessionVideoForm
from speakers.media import can_delete, can_download, can_upload
from speakers.models import ActivityLog, ChecklistItem, MediaAsset, Session
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


@pytest.mark.django_db
class TestVideoCard:
    """The video's public side on the session page: a card for every reader
    once the session will have a video, with a form on it for whoever may
    publish session videos, running the program or not."""

    def url(self, session):
        return reverse("speakers:session_video", args=[session.slug])

    def test_a_recordings_member_sets_the_link_on_the_session_page(
        self, client, conference, enabled
    ):
        vic = account("vic", "Recordings")
        session = make_session(conference, delivery=Delivery.PRE_RECORDED)
        client.force_login(vic)
        page = client.get(session.get_absolute_url())
        assert page.status_code == 200
        form = page.context["video_form"]
        assert list(form.fields) == [
            "youtube_url",
            "youtube_publish_at",
            "premiere_location",
        ]
        response = client.post(
            self.url(session),
            {
                "youtube_url": "https://youtu.be/abc",
                "youtube_publish_at": "2026-11-18T18:30",
                "premiere_location": PremiereLocation.YOUTUBE,
            },
            follow=True,
        )
        assert "Saved the video details." in response.content.decode()
        session.refresh_from_db()
        assert session.youtube_url == "https://youtu.be/abc"
        assert session.youtube_publish_at is not None
        assert session.premiere_location == PremiereLocation.YOUTUBE
        entry = ActivityLog.objects.get(action="session.video_changed")
        assert entry.actor == vic and entry.data["fields"] == [
            "premiere_location",
            "youtube_publish_at",
            "youtube_url",
        ]
        assert not vic.has_perm("speakers.manage_program")

    def test_readers_see_the_link_without_the_form(self, client, conference, enabled):
        session = make_session(
            conference,
            delivery=Delivery.PRE_RECORDED,
            youtube_url="https://y/t",
            premiere_location=PremiereLocation.YOUTUBE,
        )
        client.force_login(holding("val", "view_program"))
        page = client.get(session.get_absolute_url())
        assert page.context["video_form"] is None
        html = page.content.decode()
        assert 'id="video-link"' in html and 'href="https://y/t"' in html
        # The premiere reads as people say it, not as it is stored.
        assert "YouTube Premiere" in html and "YOUTUBE" not in html
        assert client.post(self.url(session), {"youtube_url": "x"}).status_code == 403

    def test_a_live_session_gets_a_link_only_when_the_team_records(
        self, client, conference, enabled
    ):
        client.force_login(account("vic", "Recordings"))
        session = make_session(conference, delivery=Delivery.LIVE)
        page = client.get(session.get_absolute_url())
        assert page.context["video_form"] is None
        assert 'id="video-link"' not in page.content.decode()
        assert client.post(self.url(session), {}).status_code == 404
        enabled.recordings = Recordings.TEAM
        enabled.save()
        page = client.get(session.get_absolute_url())
        assert list(page.context["video_form"].fields) == [
            "youtube_url",
            "youtube_publish_at",
        ]
        response = client.post(
            self.url(session), {"youtube_url": "https://youtu.be/live"}, follow=True
        )
        assert "Saved the video details." in response.content.decode()

    def test_the_publish_time_is_in_the_event_timezone(
        self, client, conference, enabled
    ):
        enabled.conference_timezone = "America/Los_Angeles"
        enabled.save()
        client.force_login(account("vic", "Recordings"))
        session = make_session(conference, delivery=Delivery.PRE_RECORDED)
        client.post(
            self.url(session),
            {
                "youtube_url": "https://youtu.be/t",
                "youtube_publish_at": "2026-06-01T09:00",
            },
        )
        session.refresh_from_db()
        assert session.youtube_publish_at == datetime(
            2026, 6, 1, 16, 0, tzinfo=timezone.utc
        )
        page = client.get(session.get_absolute_url())
        html = page.content.decode()
        assert 'value="2026-06-01T09:00"' in html and "In America/Los_Angeles." in html
        # Only the link changes: the unchanged publish time is not logged,
        # and a save that changes nothing is not logged at all.
        ActivityLog.objects.all().delete()
        for link in ("https://youtu.be/u", "https://youtu.be/u"):
            client.post(
                self.url(session),
                {"youtube_url": link, "youtube_publish_at": "2026-06-01T09:00"},
            )
        entry = ActivityLog.objects.get(action="session.video_changed")
        assert entry.data["fields"] == ["youtube_url"]
        client.force_login(holding("val", "view_program"))
        html = client.get(session.get_absolute_url()).content.decode()
        assert "1 Jun 2026 09:00 America/Los_Angeles" in html
        # The session form reads the same field the same way.
        client.force_login(account("ora", "Organizers"))
        form = client.get(reverse("speakers:session_edit", args=[session.slug]))
        assert 'value="2026-06-01T09:00"' in form.content.decode()

    def test_the_card_saves_when_the_session_has_other_problems(
        self, client, conference, enabled
    ):
        session = make_session(conference, delivery=Delivery.PRE_RECORDED)
        link = add_presenter(session, make_presenter(conference))
        # The type stopped allowing a role a presenter still holds:
        # Session.clean objects, but not to anything the card edits.
        session.kind.roles.remove(link.role)
        client.force_login(account("vic", "Recordings"))
        response = client.post(
            self.url(session), {"youtube_url": "https://youtu.be/x"}, follow=True
        )
        assert "Saved the video details." in response.content.decode()
        session.refresh_from_db()
        assert session.youtube_url == "https://youtu.be/x"

    def test_the_models_own_field_check_still_applies(
        self, client, conference, enabled, monkeypatch
    ):
        def refuse(session, exclude=None):
            raise ValidationError({"youtube_url": "Not that channel."})

        monkeypatch.setattr(Session, "clean_fields", refuse)
        client.force_login(account("vic", "Recordings"))
        session = make_session(conference, delivery=Delivery.PRE_RECORDED)
        response = client.post(
            self.url(session), {"youtube_url": "https://youtu.be/x"}, follow=True
        )
        assert "YouTube link: Not that channel." in response.content.decode()

    def test_an_error_without_a_field_is_reported(
        self, client, conference, enabled, monkeypatch
    ):
        def refuse(form):
            form.add_error(None, "Not now.")

        monkeypatch.setattr(SessionVideoForm, "clean", refuse)
        client.force_login(account("vic", "Recordings"))
        session = make_session(conference, delivery=Delivery.PRE_RECORDED)
        response = client.post(self.url(session), {}, follow=True)
        assert "Could not save the video details: Not now." in (
            response.content.decode()
        )

    def test_a_refused_value_is_reported(self, client, conference, enabled):
        client.force_login(account("vic", "Recordings"))
        session = make_session(conference, delivery=Delivery.PRE_RECORDED)
        response = client.post(
            self.url(session), {"youtube_url": "not a link"}, follow=True
        )
        assert "Could not save the video details: YouTube link: Enter a valid URL." in (
            response.content.decode()
        )
        # Pre-recorded delivery came from the type; a live session in an
        # edition where speakers pre-record has no video to link.
        session.delivery = Delivery.LIVE
        session.save()
        enabled.event_format = EventFormat.IN_PERSON
        enabled.recordings = Recordings.TEAM
        enabled.save()
        page = client.get(session.get_absolute_url())
        assert "premiere_location" not in page.context["video_form"].fields


@pytest.mark.django_db
class TestSessionPageItemBoxes:
    """A box on the session page for each item its viewer may act on, the
    rule the status view applies."""

    def test_a_team_ticks_the_items_it_carries(self, client, conference):
        make_settings(conference)
        member = on_team(User.objects.create_user(username="noor"), "Recordings")
        reviewer = on_team(
            User.objects.create_user(username="rev"), "Proposal reviewers"
        )
        session = make_session(conference)
        recordings = Team.objects.get(short_name="Recordings")
        theirs = ChecklistItem.objects.create(
            conference=conference,
            session=session,
            owner=ItemOwner.ORGANIZER,
            title="Edit the recording",
            team=recordings,
        )
        other = ChecklistItem.objects.create(
            conference=conference,
            session=session,
            owner=ItemOwner.ORGANIZER,
            title="Book the room",
        )
        url = reverse("speakers:session_detail", args=[session.slug])
        status_url = "speakers:item_status"
        client.force_login(member)
        page = client.get(url).content.decode()
        assert reverse(status_url, args=[theirs.pk]) in page
        assert reverse(status_url, args=[other.pk]) not in page
        client.force_login(reviewer)
        page = client.get(url).content.decode()
        assert reverse(status_url, args=[theirs.pk]) not in page
