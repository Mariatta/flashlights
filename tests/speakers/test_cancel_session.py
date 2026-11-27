"""Organizers cancel a session and bring it back: what leaves the program,
who is told, and what happens to its checklist and its slot."""

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from common.models import SentEmail
from speakers.checklists import add_adhoc_item, complete_item, skip_item
from speakers.constants import (
    AutoRule,
    ItemOwner,
    ItemStatus,
    ProgramVisibility,
    SessionStatus,
)
from speakers.emails import (
    SESSION_CANCELLED_TEMPLATE,
    SESSION_RESTORED_TEMPLATE,
    signed_invitation_token,
)
from speakers.feeds import presenter_feed_token
from speakers.models import (
    ActivityLog,
    InvitationStatus,
    ScheduleSlot,
    SpeakerSettings,
)
from speakers.public import public_program
from speakers.reminders import send_checklist_digests
from speakers.services import (
    InvitationError,
    SessionError,
    accept_invitation,
    cancel_session,
    restore_session,
    send_invitation,
)
from speakers.tasks import (
    send_session_cancelled_email_task,
    send_session_restored_email_task,
)

from .factories import (
    add_presenter,
    make_invitation,
    make_presenter,
    make_proposal,
    make_published_slot,
    make_room,
    make_session,
    make_settings,
    make_slot,
)

T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)
FEED = reverse("speakers:schedule_feed")


@pytest.fixture
def enabled(conference):
    return make_settings(conference, program_visibility=ProgramVisibility.PUBLISHED)


@pytest.fixture
def organizer(db, grant_organizer):
    return grant_organizer(
        User.objects.create_user(username="organizer", email="org@example.com")
    )


@pytest.fixture
def run(django_capture_on_commit_callbacks):
    """Call a service and run its commit hooks, so its emails go out."""

    def _run(service, *args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return service(*args, **kwargs)

    return _run


def confirmed_session(conference, title="Django 101", speakers=("Ada",)):
    """A confirmed session with its speakers, each confirmed on it."""
    session = make_session(conference, title=title, kind="PANEL")
    for name in speakers:
        add_presenter(
            session,
            make_presenter(
                conference, display_name=name, email=f"{name.lower()}@example.com"
            ),
            confirmed=True,
        )
    session.confirm()
    return session


def published_session(conference, room=None, **kwargs):
    """On the public schedule: a slot, its published copy, and public."""
    session = confirmed_session(conference, **kwargs)
    make_slot(session, room=room, start_utc=T0)
    make_published_slot(session)
    session.schedule()
    session.publish()
    return session


def item_for(session, title, presenter=None, **kwargs):
    return add_adhoc_item(
        session.conference,
        title,
        ItemOwner.SPEAKER,
        presenter=presenter,
        session=session,
        **kwargs,
    )


def cancel_url(session):
    return reverse("speakers:session_cancel", args=[session.slug])


def restore_url(session):
    return reverse("speakers:session_restore", args=[session.slug])


@pytest.mark.django_db
class TestCancelSession:
    def test_it_leaves_the_program_and_closes_its_checklist(
        self, conference, enabled, organizer, run
    ):
        session = published_session(conference, speakers=("Ada", "Grace"))
        ada = session.session_presenters.first().presenter
        todo = item_for(session, "Send your slides", presenter=ada)
        done = item_for(session, "Sign", presenter=ada)
        complete_item(done)
        team_item = item_for(session, "Book the room")
        other = confirmed_session(conference, title="Another", speakers=("Zed",))
        untouched = item_for(other, "Elsewhere")
        mail.outbox.clear()

        entry = run(cancel_session, session, actor=organizer, reason="Speaker is ill")

        session.refresh_from_db()
        assert session.status == SessionStatus.CANCELLED
        assert session.is_public is False
        assert session not in public_program(conference)
        for item in (todo, done, team_item, untouched):
            item.refresh_from_db()
        assert todo.status == ItemStatus.SKIPPED
        assert team_item.status == ItemStatus.SKIPPED
        assert done.status == ItemStatus.DONE
        assert untouched.status == ItemStatus.TODO
        assert entry.action == "session.cancelled"
        assert entry.actor == organizer and entry.message == "Speaker is ill"
        assert entry.data["skipped_item_ids"] == [todo.pk, team_item.pk]
        assert entry.data["previous_status"] == SessionStatus.PUBLISHED
        assert entry.data["was_public"] is True
        assert entry.data["emailed"] == 2
        # The slot stays as a record.
        assert ScheduleSlot.objects.filter(session=session).exists()
        assert sorted(m.to[0] for m in mail.outbox) == [
            "ada@example.com",
            "grace@example.com",
        ]

    def test_the_feeds_say_cancelled(self, client, conference, enabled, organizer):
        session = published_session(conference, title="Called off")
        presenter = session.session_presenters.get().presenter
        assert "Called off" in client.get(FEED).content.decode()
        cancel_session(session, actor=organizer)
        assert "Called off" not in client.get(FEED).content.decode()
        personal = client.get(
            reverse("speakers:presenter_feed", args=[presenter_feed_token(presenter)])
        ).content.decode()
        assert "Called off" in personal and "STATUS:CANCELLED" in personal

    def test_the_email_carries_the_note_and_not_the_reason(
        self, conference, enabled, organizer, run
    ):
        SpeakerSettings.objects.filter(conference=conference).update(
            organizers_email="team@example.com"
        )
        session = confirmed_session(conference)
        mail.outbox.clear()
        run(
            cancel_session,
            session,
            actor=organizer,
            reason="Double booked the room",
            note="We are **so sorry** about this.",
        )
        (message,) = mail.outbox
        assert message.to == ["ada@example.com"]
        assert message.reply_to == ["team@example.com"]
        assert "Your session was cancelled: Django 101" in message.subject
        assert "has been cancelled" in message.body
        assert "A note from the organizing team" in message.body
        assert "so sorry" in message.body
        assert "Double booked" not in message.body
        assert "/speakers/me/" in message.body
        record = SentEmail.objects.get(template=SESSION_CANCELLED_TEMPLATE)
        assert record.context_digest["session"] == session.pk

    def test_without_a_note_the_email_has_no_note_line(
        self, conference, enabled, organizer, run
    ):
        session = confirmed_session(conference)
        mail.outbox.clear()
        run(cancel_session, session, actor=organizer)
        assert "A note from the organizing team" not in mail.outbox[0].body

    def test_only_speakers_who_said_yes_are_told(
        self, conference, enabled, organizer, run
    ):
        session = confirmed_session(conference)
        add_presenter(session, make_presenter(conference, email="notyet@example.com"))
        mail.outbox.clear()
        entry = run(cancel_session, session, actor=organizer)
        assert [m.to for m in mail.outbox] == [["ada@example.com"]]
        assert entry.data["emailed"] == 1

    def test_quietly_when_asked(self, conference, enabled, organizer, run):
        session = confirmed_session(conference)
        mail.outbox.clear()
        entry = run(cancel_session, session, actor=organizer, notify=False)
        assert mail.outbox == []
        assert entry.data["emailed"] == 0

    def test_refused_twice_and_for_a_proposal(self, conference, enabled, organizer):
        session = confirmed_session(conference)
        cancel_session(session, actor=organizer)
        with pytest.raises(SessionError, match="already cancelled"):
            cancel_session(session, actor=organizer)
        proposed = make_session(conference, status=SessionStatus.PROPOSED)
        with pytest.raises(SessionError, match="still a proposal"):
            cancel_session(proposed, actor=organizer)
        assert ActivityLog.objects.filter(action="session.cancelled").count() == 1

    def test_a_waiting_or_automatic_item_is_skipped_too(
        self, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        waiting = item_for(session, "Later")
        automatic = item_for(session, "Scheduled")
        type(waiting).objects.filter(pk=waiting.pk).update(is_waiting=True)
        type(automatic).objects.filter(pk=automatic.pk).update(
            auto_complete_rule=AutoRule.SESSION_SCHEDULED
        )
        cancel_session(session, actor=organizer)
        waiting.refresh_from_db()
        automatic.refresh_from_db()
        assert waiting.status == ItemStatus.SKIPPED
        assert automatic.status == ItemStatus.SKIPPED

    def test_the_cost_does_not_grow_with_the_speakers(
        self, conference, enabled, organizer
    ):
        """One read for the speakers, however many there are."""
        counts = []
        for names in (("Ada",), ("Bea", "Cy", "Di")):
            session = confirmed_session(conference, title=names[0], speakers=names)
            with CaptureQueriesContext(connection) as queries:
                cancel_session(session, actor=organizer)
            counts.append(len(queries))
        assert counts[0] == counts[1]


@pytest.mark.django_db
class TestOpenInvitation:
    """Someone invited who has not answered when the session is cancelled."""

    @pytest.fixture
    def invitation(self, conference, enabled):
        session = make_session(conference, title="Invited", kind="PANEL")
        presenter = make_presenter(conference, email="late@example.com")
        add_presenter(session, presenter)
        invitation = make_invitation(presenter, session)
        send_invitation(invitation)
        return invitation

    def url(self, invitation):
        return reverse(
            "speakers:invitation", args=[signed_invitation_token(invitation)]
        )

    def test_the_link_says_the_session_is_cancelled(
        self, client, invitation, organizer
    ):
        cancel_session(invitation.session, actor=organizer)
        url = self.url(invitation)
        page = client.get(url)
        assert 'data-reason="session_cancelled"' in page.content.decode()
        assert "has been cancelled" in page.content.decode()
        page = client.post(url, {"action": "accept"})
        assert 'data-reason="session_cancelled"' in page.content.decode()
        invitation.refresh_from_db()
        # Still open and unanswered: nobody was confirmed on a session
        # that is off.
        assert invitation.status == InvitationStatus.SENT
        assert invitation.opened_at is None
        link = invitation.session.session_presenters.get()
        assert link.confirmed_at is None
        assert not mail.outbox[1:]

    def test_accepting_is_refused_whoever_calls(self, invitation, organizer):
        cancel_session(invitation.session, actor=organizer)
        with pytest.raises(InvitationError, match="session_cancelled"):
            accept_invitation(invitation)
        assert invitation.session.session_presenters.get().confirmed_at is None

    def test_the_link_works_again_once_restored(self, client, invitation, organizer):
        cancel_session(invitation.session, actor=organizer)
        restore_session(invitation.session, actor=organizer)
        response = client.post(self.url(invitation), {"action": "accept"})
        assertRedirects(
            response, reverse("speakers:index"), fetch_redirect_response=False
        )
        assert invitation.session.session_presenters.get().confirmed_at is not None


@pytest.mark.django_db
class TestReminders:
    def test_nobody_is_chased_for_a_cancelled_session(
        self, conference, enabled, organizer
    ):
        """Cancelling skips the open items; one opened by hand afterwards
        is still left out of the digest."""
        session = confirmed_session(conference)
        ada = session.session_presenters.get().presenter
        due = (datetime.now(tz=timezone.utc) + timedelta(days=3)).date()
        item = item_for(session, "Send your slides", presenter=ada, due_date=due)
        mail.outbox.clear()
        assert send_checklist_digests(conference) == 1
        cancel_session(session, actor=organizer, notify=False)
        type(item).objects.filter(pk=item.pk).update(status=ItemStatus.TODO)
        type(item).objects.filter(pk=item.pk).first().reminders.all().delete()
        mail.outbox.clear()
        assert send_checklist_digests(conference) == 0
        assert mail.outbox == []


@pytest.mark.django_db
class TestRestoreSession:
    def test_back_to_confirmed_with_its_items_and_an_email(
        self, conference, enabled, organizer, run
    ):
        session = confirmed_session(conference)
        ada = session.session_presenters.get().presenter
        todo = item_for(session, "Send your slides", presenter=ada)
        by_hand = item_for(session, "Not needed", presenter=ada)
        skip_item(by_hand)
        cancel_session(session, actor=organizer, notify=False)
        mail.outbox.clear()

        entry = run(restore_session, session, actor=organizer)

        session.refresh_from_db()
        assert session.status == SessionStatus.CONFIRMED
        assert session.is_public is False
        todo.refresh_from_db()
        by_hand.refresh_from_db()
        assert todo.status == ItemStatus.TODO
        # Skipped before the cancellation, so not the cancellation's to reopen.
        assert by_hand.status == ItemStatus.SKIPPED
        assert entry.action == "session.restored" and entry.actor == organizer
        assert entry.data == {
            "reopened_item_ids": [todo.pk],
            "slot_dropped": False,
            "emailed": 1,
        }
        (message,) = mail.outbox
        assert message.to == ["ada@example.com"]
        assert "Your session is back on: Django 101" in message.subject
        assert "back on the program" in message.body
        assert "not scheduled yet" not in message.body
        assert f"/speakers/me/sessions/{session.slug}/" in message.body
        assert SentEmail.objects.filter(template=SESSION_RESTORED_TEMPLATE).exists()

    def test_only_a_cancelled_session(self, conference, enabled, organizer):
        session = confirmed_session(conference)
        with pytest.raises(SessionError, match="Only a cancelled session"):
            restore_session(session, actor=organizer)

    def test_an_item_reopened_by_hand_meanwhile_is_left_alone(
        self, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        item = item_for(session, "Send your slides")
        cancel_session(session, actor=organizer, notify=False)
        type(item).objects.filter(pk=item.pk).update(status=ItemStatus.DONE)
        entry = restore_session(session, actor=organizer, notify=False)
        item.refresh_from_db()
        assert item.status == ItemStatus.DONE
        assert entry.data["reopened_item_ids"] == []
        assert entry.data["emailed"] == 0

    def test_a_required_item_open_again_keeps_it_a_draft(
        self, conference, enabled, organizer
    ):
        session = make_session(conference, title="Blocked", kind="PANEL")
        add_presenter(session, make_presenter(conference), confirmed=True)
        item = item_for(session, "Sign the form")
        type(item).objects.filter(pk=item.pk).update(is_required=True)
        cancel_session(session, actor=organizer, notify=False)
        restore_session(session, actor=organizer, notify=False)
        session.refresh_from_db()
        assert session.status == SessionStatus.DRAFT

    def test_an_open_invitation_makes_it_invited_again(
        self, conference, enabled, organizer
    ):
        session = make_session(conference, title="Invited", kind="PANEL")
        presenter = make_presenter(conference)
        add_presenter(session, presenter)
        send_invitation(make_invitation(presenter, session))
        session.refresh_from_db()
        assert session.status == SessionStatus.INVITED
        cancel_session(session, actor=organizer)
        restore_session(session, actor=organizer)
        session.refresh_from_db()
        assert session.status == SessionStatus.INVITED

    def test_a_rule_that_holds_ticks_its_item_again(
        self, conference, enabled, organizer
    ):
        """An item that completes itself is evaluated on the way back, and
        the confirmation it unblocks is not run a second time."""
        session = make_session(conference, title="Automatic", kind="PANEL")
        add_presenter(session, make_presenter(conference), confirmed=True)
        make_slot(session, start_utc=T0)
        item = item_for(session, "Session scheduled")
        type(item).objects.filter(pk=item.pk).update(
            is_required=True, auto_complete_rule=AutoRule.SESSION_SCHEDULED
        )
        cancel_session(session, actor=organizer, notify=False)
        make_published_slot(session)
        restore_session(session, actor=organizer, notify=False)
        item.refresh_from_db()
        session.refresh_from_db()
        assert item.status == ItemStatus.DONE
        # Confirmed by the tick, then scheduled because its slot is kept.
        assert session.status == SessionStatus.SCHEDULED
        confirmed = ActivityLog.for_target(session).filter(action="session.confirmed")
        assert confirmed.count() == 1

    def test_a_program_item_is_confirmed_again(self, conference, enabled, organizer):
        coffee = make_session(
            conference, title="Coffee", kind="BREAK", status=SessionStatus.CONFIRMED
        )
        cancel_session(coffee, actor=organizer)
        restore_session(coffee, actor=organizer)
        coffee.refresh_from_db()
        assert coffee.status == SessionStatus.CONFIRMED

    def test_a_program_item_with_a_required_item_open_stays_a_draft(
        self, conference, enabled, organizer
    ):
        coffee = make_session(
            conference, title="Coffee", kind="BREAK", status=SessionStatus.CONFIRMED
        )
        item = item_for(coffee, "Order the coffee")
        type(item).objects.filter(pk=item.pk).update(is_required=True)
        cancel_session(coffee, actor=organizer)
        restore_session(coffee, actor=organizer)
        coffee.refresh_from_db()
        assert coffee.status == SessionStatus.DRAFT

    def test_a_free_slot_is_kept_and_it_is_scheduled_again(
        self, conference, enabled, organizer
    ):
        session = published_session(conference, room=make_room(conference))
        cancel_session(session, actor=organizer, notify=False)
        entry = restore_session(session, actor=organizer, notify=False)
        session.refresh_from_db()
        assert entry.data["slot_dropped"] is False
        assert ScheduleSlot.objects.filter(session=session).exists()
        # The speakers' schedule still carries it, so it is scheduled as it
        # was; going public again is the organizers' own step.
        assert session.status == SessionStatus.SCHEDULED
        assert session.is_public is False

    def test_a_slot_taken_meanwhile_is_dropped_and_the_email_says_so(
        self, conference, enabled, organizer, run
    ):
        room = make_room(conference)
        session = published_session(conference, room=room)
        cancel_session(session, actor=organizer, notify=False)
        other = confirmed_session(conference, title="Took its place", speakers=("Zed",))
        make_slot(other, room=room, start_utc=T0)
        mail.outbox.clear()
        entry = run(restore_session, session, actor=organizer)
        session.refresh_from_db()
        assert entry.data["slot_dropped"] is True
        assert not ScheduleSlot.objects.filter(session=session).exists()
        assert ScheduleSlot.objects.filter(session=other).exists()
        assert session.status == SessionStatus.CONFIRMED
        assert "not scheduled yet" in mail.outbox[0].body

    def test_without_a_cancellation_on_record(self, conference, enabled, organizer):
        """Cancelled by hand in the admin: nothing to reopen, still restored."""
        session = confirmed_session(conference)
        item = item_for(session, "Send your slides")
        session.cancel()
        entry = restore_session(session, actor=organizer, notify=False)
        item.refresh_from_db()
        session.refresh_from_db()
        assert session.status == SessionStatus.CONFIRMED
        assert item.status == ItemStatus.TODO
        assert entry.data["reopened_item_ids"] == []

    def test_cancelled_again_reopens_only_the_latest_set(
        self, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        first = item_for(session, "First")
        cancel_session(session, actor=organizer, notify=False)
        restore_session(session, actor=organizer, notify=False)
        skip_item(first)
        second = item_for(session, "Second")
        cancel_session(session, actor=organizer, notify=False)
        entry = restore_session(session, actor=organizer, notify=False)
        first.refresh_from_db()
        assert first.status == ItemStatus.SKIPPED
        assert entry.data["reopened_item_ids"] == [second.pk]


@pytest.mark.django_db
class TestEmailTasks:
    def test_cancelled_is_sent_once(self, conference, enabled, organizer):
        session = confirmed_session(conference)
        presenter = session.session_presenters.get().presenter
        entry = cancel_session(session, actor=organizer, note="Sorry")
        mail.outbox.clear()
        args = (session.pk, presenter.pk, entry.pk)
        assert "Sent cancellation" in send_session_cancelled_email_task(*args)
        assert "already sent" in send_session_cancelled_email_task(*args)
        assert len(mail.outbox) == 1 and "Sorry" in mail.outbox[0].body

    def test_cancelled_is_not_sent_once_restored_or_gone(
        self, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        presenter = session.session_presenters.get().presenter
        entry = cancel_session(session, actor=organizer)
        restore_session(session, actor=organizer)
        mail.outbox.clear()
        assert "no longer cancelled" in send_session_cancelled_email_task(
            session.pk, presenter.pk, entry.pk
        )
        assert "Nothing to send" in send_session_cancelled_email_task(
            session.pk, 0, entry.pk
        )
        assert mail.outbox == []

    def test_restored_is_sent_once(self, conference, enabled, organizer):
        session = confirmed_session(conference)
        presenter = session.session_presenters.get().presenter
        cancel_session(session, actor=organizer)
        entry = restore_session(session, actor=organizer)
        mail.outbox.clear()
        args = (session.pk, presenter.pk, entry.pk)
        assert "Sent restore" in send_session_restored_email_task(*args)
        assert "already sent" in send_session_restored_email_task(*args)
        assert len(mail.outbox) == 1

    def test_restored_is_not_sent_once_cancelled_again_or_gone(
        self, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        presenter = session.session_presenters.get().presenter
        cancel_session(session, actor=organizer)
        entry = restore_session(session, actor=organizer)
        cancel_session(session, actor=organizer)
        mail.outbox.clear()
        assert "cancelled again" in send_session_restored_email_task(
            session.pk, presenter.pk, entry.pk
        )
        assert "Nothing to send" in send_session_restored_email_task(
            session.pk, presenter.pk, 0
        )
        assert mail.outbox == []

    def test_each_cancellation_mails_again(self, conference, enabled, organizer, run):
        session = confirmed_session(conference)
        mail.outbox.clear()
        run(cancel_session, session, actor=organizer)
        run(restore_session, session, actor=organizer)
        run(cancel_session, session, actor=organizer)
        subjects = [m.subject for m in mail.outbox]
        assert len(subjects) == 3
        assert sum("was cancelled" in s for s in subjects) == 2


@pytest.mark.django_db
class TestCancelPages:
    def test_only_whoever_runs_the_program(
        self, client, conference, enabled, join_team
    ):
        liaison = join_team(
            User.objects.create_user(username="lena", email="lena@example.com"),
            "Speaker liaisons",
        )
        reviewer = join_team(
            User.objects.create_user(username="rae", email="rae@example.com"),
            "Proposal reviewers",
        )
        session = make_session(conference, title="Liaised", kind="PANEL")
        add_presenter(
            session, make_presenter(conference, liaison=liaison), confirmed=True
        )
        session.confirm()
        assertRedirects(
            client.get(cancel_url(session)),
            reverse("account_login") + "?next=" + cancel_url(session),
        )
        for user in (liaison, reviewer):
            client.force_login(user)
            page = client.get(session.get_absolute_url()).content.decode()
            assert "Cancel this session" not in page
            assert client.get(cancel_url(session)).status_code == 403
            assert client.post(cancel_url(session)).status_code == 403
        session.cancel()
        for user in (liaison, reviewer):
            client.force_login(user)
            page = client.get(session.get_absolute_url()).content.decode()
            assert "This session is cancelled" in page
            assert restore_url(session) not in page
            assert client.post(restore_url(session)).status_code == 403
        session.refresh_from_db()
        assert session.status == SessionStatus.CANCELLED

    def test_the_page_says_what_will_happen(
        self, client, conference, enabled, organizer
    ):
        session = published_session(conference, speakers=("Ada", "Grace"))
        item_for(session, "Send your slides")
        client.force_login(organizer)
        detail = client.get(session.get_absolute_url()).content.decode()
        assert cancel_url(session) in detail
        assert "This session is cancelled" not in detail
        page = client.get(cancel_url(session)).content.decode()
        assert "2 speakers are emailed now:" in page
        assert "Ada, Grace" in page
        assert "1 open checklist item is skipped" in page
        assert "Its slot stays as a record" in page
        assert "Only organizers see it" in page

    def test_the_page_for_a_session_nobody_confirmed_on(
        self, client, conference, enabled, organizer
    ):
        session = make_session(conference, title="Empty", kind="PANEL")
        client.force_login(organizer)
        page = client.get(cancel_url(session)).content.decode()
        assert "Nobody is emailed" in page
        assert "0 open checklist items are skipped" in page
        assert "Its slot stays as a record" not in page

    def test_cancel_then_restore(self, client, conference, enabled, organizer):
        session = published_session(conference)
        item_for(session, "Send your slides")
        client.force_login(organizer)
        mail.outbox.clear()
        response = client.post(
            cancel_url(session),
            {"reason": "Speaker is ill", "note": "Get well soon."},
            follow=True,
        )
        assertRedirects(response, session.get_absolute_url())
        page = response.content.decode()
        assert "1 speaker(s) are being emailed and 1 open checklist item(s)" in page
        assert "This session is cancelled" in page
        assert restore_url(session) in page
        assert cancel_url(session) not in page
        # Who and why, on the organizers' page only.
        assert "Cancelled by" in page
        assert "Reason: Speaker is ill" in page
        assert "Get well soon." in mail.outbox[0].body
        session.refresh_from_db()
        assert session.status == SessionStatus.CANCELLED

        mail.outbox.clear()
        response = client.post(restore_url(session), follow=True)
        page = response.content.decode()
        assert "Restored “Django 101” as scheduled." in page
        assert "1 checklist item(s) reopened and 1 speaker(s) are being emailed" in page
        assert "until it is published again" in page
        assert "slot was removed" not in page
        assert len(mail.outbox) == 1

    def test_a_cancellation_by_the_portal_names_nobody(
        self, client, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        cancel_session(session)
        client.force_login(organizer)
        page = client.get(session.get_absolute_url()).content.decode()
        assert "Cancelled on" in page
        assert "Cancelled by" not in page and "Reason:" not in page

    def test_the_speaker_sees_it_cancelled_with_nothing_left_to_do(
        self, client, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        presenter = session.session_presenters.get().presenter
        presenter.user = User.objects.create_user(
            username="ada", email="ada@example.com"
        )
        presenter.save()
        item_for(session, "Send your slides", presenter=presenter)
        cancel_session(session, actor=organizer, reason="Not for the speaker")
        client.force_login(presenter.user)
        page = client.get(reverse("speakers:my_dashboard")).content.decode()
        assert "Django 101" in page and "Cancelled" in page
        assert "Not for the speaker" not in page
        assert "Send your slides" not in page

    def test_restore_says_when_the_slot_went(
        self, client, conference, enabled, organizer
    ):
        room = make_room(conference)
        session = published_session(conference, room=room)
        cancel_session(session, actor=organizer)
        other = confirmed_session(conference, title="Took its place", speakers=("Zed",))
        make_slot(other, room=room, start_utc=T0)
        client.force_login(organizer)
        page = client.post(restore_url(session), follow=True).content.decode()
        assert "its slot was removed: place it on the schedule again" in page

    def test_refusals_come_back_as_messages(
        self, client, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        client.force_login(organizer)
        page = client.post(restore_url(session), follow=True).content.decode()
        assert "Only a cancelled session can be restored." in page
        session.cancel()
        page = client.get(cancel_url(session), follow=True).content.decode()
        assert "This session is already cancelled." in page
        page = client.post(cancel_url(session), follow=True).content.decode()
        assert "This session is already cancelled." in page

    def test_a_proposal_is_answered_not_cancelled(
        self, client, conference, enabled, organizer
    ):
        session = make_session(conference, status=SessionStatus.PROPOSED)
        presenter = make_presenter(conference)
        add_presenter(session, presenter)
        make_proposal(session, presenter)
        client.force_login(organizer)
        detail = client.get(session.get_absolute_url()).content.decode()
        assert cancel_url(session) not in detail
        page = client.get(cancel_url(session), follow=True).content.decode()
        assert "still a proposal" in page

    def test_an_over_long_reason_is_refused_on_the_page(
        self, client, conference, enabled, organizer
    ):
        session = confirmed_session(conference)
        client.force_login(organizer)
        response = client.post(cancel_url(session), {"reason": "x" * 501})
        assert response.status_code == 200
        assert "at most 500 characters" in response.content.decode()
        session.refresh_from_db()
        assert session.status == SessionStatus.CONFIRMED

    def test_another_editions_session_is_not_found(
        self, client, conference, enabled, organizer
    ):
        client.force_login(organizer)
        assert client.get(cancel_url_for("nope")).status_code == 404
        assert client.post(restore_url_for("nope")).status_code == 404


def cancel_url_for(slug):
    return reverse("speakers:session_cancel", args=[slug])


def restore_url_for(slug):
    return reverse("speakers:session_restore", args=[slug])
