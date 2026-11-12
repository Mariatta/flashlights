"""The overlap rules on the schedule grid (task 4.1, design §8.5).

Two slots may not share a room, and an all-room band blocks the whole
grid, except that two program-kind bands may coexist. A presenter booked
twice at once is a warning, never an error.
"""

import importlib
from datetime import datetime, timedelta, timezone

import pytest
from django.apps import apps
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models.signals import post_save
from django.test.utils import CaptureQueriesContext

from portal.models import Conference
from speakers import api
from speakers.models import ScheduleSlot, Session, SpeakerSettings

from .factories import (
    add_presenter,
    make_presenter,
    make_room,
    make_session,
    make_slot,
)

T0 = datetime(2026, 12, 5, 14, 0, tzinfo=timezone.utc)

step_migration = importlib.import_module("speakers.migrations.0024_schedule_step")


@pytest.fixture
def other_conference(db):
    return Conference.objects.create(year=2024, name="Flashlights 2024", slug="2024")


def place(session, minutes=0, length=None, **kwargs):
    """A slot ``minutes`` after two o'clock, ``length`` minutes long.

    Without ``length`` the end defaults from the session duration, as in
    production (a workshop runs 90 minutes, a break 15).
    """
    kwargs["start_utc"] = T0 + timedelta(minutes=minutes)
    if length is not None:
        kwargs["end_utc"] = kwargs["start_utc"] + timedelta(minutes=length)
    return make_slot(session, **kwargs)


@pytest.mark.django_db
class TestChannelOverlap:
    def test_two_slots_on_one_room_may_not_overlap(self, conference):
        room = make_room(conference)
        place(make_session(conference, title="Shapely tables"), room=room)
        with pytest.raises(ValidationError) as excinfo:
            place(make_session(conference), minutes=60, room=room)
        assert "Shapely tables" in str(excinfo.value)
        assert "14:00 to 15:30 UTC" in str(excinfo.value)
        assert ScheduleSlot.objects.count() == 1

    def test_back_to_back_slots_are_fine(self, conference):
        room = make_room(conference)
        place(make_session(conference), room=room)
        place(make_session(conference), minutes=90, room=room)
        assert ScheduleSlot.objects.count() == 2

    def test_parallel_rooms_are_fine(self, conference):
        place(make_session(conference), room=make_room(conference))
        place(make_session(conference), room=make_room(conference))
        assert ScheduleSlot.objects.count() == 2

    def test_moving_a_slot_does_not_collide_with_itself(self, conference):
        slot = place(make_session(conference), room=make_room(conference))
        slot.start_utc += timedelta(minutes=15)
        slot.end_utc += timedelta(minutes=15)
        slot.save()
        assert ScheduleSlot.objects.get(pk=slot.pk).start_utc == T0 + timedelta(
            minutes=15
        )

    def test_a_cancelled_session_frees_its_time(self, conference):
        room = make_room(conference)
        cancelled = make_session(conference)
        place(cancelled, room=room)
        cancelled.cancel()
        place(make_session(conference), room=room)
        assert ScheduleSlot.objects.count() == 2

    def test_another_edition_is_another_grid(self, conference, other_conference):
        place(make_session(conference))
        place(make_session(other_conference))
        assert ScheduleSlot.objects.count() == 2


@pytest.mark.django_db
class TestAllChannelBands:
    def test_a_band_blocks_a_room_slot(self, conference):
        place(make_session(conference, kind="BREAK"))
        with pytest.raises(ValidationError):
            place(make_session(conference), length=10, room=make_room(conference))

    def test_a_room_slot_blocks_a_band(self, conference):
        place(make_session(conference), room=make_room(conference))
        with pytest.raises(ValidationError):
            place(make_session(conference, kind="BREAK"))

    def test_two_program_bands_may_share_the_window(self, conference):
        place(make_session(conference, kind="BREAK"), length=60)
        place(make_session(conference, kind="SOCIAL"), minutes=15)
        assert ScheduleSlot.objects.count() == 2

    def test_a_content_band_tolerates_no_company(self, conference):
        place(make_session(conference, kind="WORKSHOP"))
        with pytest.raises(ValidationError):
            place(make_session(conference, kind="BREAK"), minutes=15)

    def test_a_program_band_still_collides_with_a_content_band(self, conference):
        place(make_session(conference, kind="BREAK"), length=60)
        with pytest.raises(ValidationError):
            place(make_session(conference, kind="WORKSHOP"), minutes=15)


@pytest.mark.django_db
class TestWindow:
    def test_the_slot_must_end_after_it_starts(self, conference):
        with pytest.raises(ValidationError) as excinfo:
            place(make_session(conference), length=0)
        assert "end_utc" in excinfo.value.message_dict

    def test_the_rules_wait_for_the_fields(self, conference):
        assert ScheduleSlot().clean() is None
        slot = ScheduleSlot(session=make_session(conference))
        with pytest.raises(ValidationError) as excinfo:
            slot.full_clean()
        assert "start_utc" in excinfo.value.message_dict


@pytest.mark.django_db
class TestPresenterClashes:
    def test_a_double_booked_presenter_is_a_warning_not_a_block(self, conference):
        ada = make_presenter(conference, display_name="Ada")
        first = make_session(conference, title="First")
        second = make_session(conference, title="Second")
        add_presenter(first, ada)
        add_presenter(second, ada)
        place(first, room=make_room(conference))
        slot = place(second, minutes=30, room=make_room(conference))
        clashes = list(slot.presenter_clashes())
        assert [(link.presenter, link.session) for link in clashes] == [(ada, first)]
        assert [link.session for link in first.slot.presenter_clashes()] == [second]

    def test_no_overlap_means_no_warning(self, conference):
        ada = make_presenter(conference)
        first = make_session(conference)
        second = make_session(conference)
        add_presenter(first, ada)
        add_presenter(second, ada)
        place(first, room=make_room(conference))
        slot = place(second, minutes=90, room=make_room(conference))
        assert list(slot.presenter_clashes()) == []

    def test_someone_elses_booking_is_not_a_clash(self, conference):
        first = make_session(conference)
        second = make_session(conference)
        add_presenter(first, make_presenter(conference))
        add_presenter(second, make_presenter(conference))
        place(first, room=make_room(conference))
        slot = place(second, minutes=30, room=make_room(conference))
        assert list(slot.presenter_clashes()) == []


@pytest.mark.django_db
class TestProposalsStayOffTheGrid:
    """An unanswered proposal cannot hold a slot (PR #458 review).

    The overlap rules look through PROPOSED and REJECTED on the other
    side, so letting one hold a slot would let approve() carry a
    quietly conflicting slot straight onto the grid.
    """

    def test_a_proposal_cannot_be_slotted(self, conference):
        from speakers.constants import SessionStatus

        proposed = make_session(conference, status=SessionStatus.PROPOSED)
        with pytest.raises(ValidationError) as excinfo:
            place(proposed)
        assert "waiting for an answer" in str(excinfo.value)
        rejected = make_session(conference, status=SessionStatus.REJECTED)
        with pytest.raises(ValidationError):
            place(rejected)
        assert ScheduleSlot.objects.count() == 0

    def test_the_reviewers_scenario_dies_at_step_one(self, conference):
        """Slot a proposal, slot a live session over it, approve: the
        first step now refuses, so approve() can never surface a
        conflicting slot."""
        from speakers.constants import SessionStatus

        proposed = make_session(conference, status=SessionStatus.PROPOSED)
        with pytest.raises(ValidationError):
            place(proposed)
        live = make_session(conference)
        place(live)
        proposed.approve()
        assert proposed.status == SessionStatus.DRAFT
        assert ScheduleSlot.objects.count() == 1

    def test_a_cancelled_sessions_slot_is_still_a_record(self, conference):
        """Cancelled is deliberately not refused: the slot stays as a
        record (its time is already freed for others)."""
        session = make_session(conference)
        slot = place(session)
        session.cancel()
        slot.save()
        assert ScheduleSlot.objects.filter(pk=slot.pk).exists()


@pytest.mark.django_db
class TestOneLength:
    """A session and its slot on the grid share one length, both ways."""

    def test_a_longer_slot_changes_the_session(self, conference):
        session = make_session(conference)
        slot = place(session, length=45)
        session.refresh_from_db()
        assert session.duration_minutes == 45
        assert slot.session.duration_minutes == 45

    def test_a_shorter_session_moves_the_slot_end(self, conference):
        session = make_session(conference)
        slot = place(session, length=30)
        session.duration_minutes = 15
        session.save()
        slot.refresh_from_db()
        assert slot.end_utc == T0 + timedelta(minutes=15)

    def test_a_blank_length_takes_the_type_default_on_the_grid_too(self, conference):
        session = make_session(conference)
        slot = place(session, length=20)
        session.duration_minutes = None
        session.save()
        slot.refresh_from_db()
        minutes = session.kind.default_duration_minutes
        assert slot.end_utc == T0 + timedelta(minutes=minutes)

    def test_saving_other_fields_leaves_the_slot_alone(self, conference):
        session = make_session(conference)
        slot = place(session, length=15)
        modified = slot.modified_date
        session.title = "Renamed"
        session.save()
        session.duration_minutes = 4
        session.save(update_fields=["title"])
        slot.refresh_from_db()
        assert slot.end_utc == T0 + timedelta(minutes=15)
        assert slot.modified_date == modified

    def test_an_unplaced_session_has_no_slot_to_move(self, conference):
        session = make_session(conference)
        session.duration_minutes = 4
        session.save()
        assert not ScheduleSlot.objects.exists()

    def test_a_length_that_would_overlap_the_next_slot_is_refused(self, conference):
        room = make_room(conference)
        session = make_session(conference)
        place(session, length=30, room=room)
        place(make_session(conference, title="Next up"), minutes=30, room=room)
        session.duration_minutes = 45
        with pytest.raises(ValidationError) as excinfo:
            session.full_clean()
        assert "Next up" in str(excinfo.value)
        assert "duration_minutes" in excinfo.value.message_dict

    def test_a_length_with_room_to_spare_is_accepted(self, conference):
        room = make_room(conference)
        session = make_session(conference)
        place(session, length=30, room=room)
        place(make_session(conference), minutes=60, room=room)
        session.duration_minutes = 60
        session.full_clean()

    def test_a_blank_length_is_checked_at_the_type_default(self, conference):
        room = make_room(conference)
        session = make_session(conference)
        place(session, length=15, room=room)
        place(make_session(conference, title="Next up"), minutes=15, room=room)
        session.duration_minutes = None
        with pytest.raises(ValidationError) as excinfo:
            session.full_clean()
        assert "Next up" in str(excinfo.value)

    def test_a_zero_length_is_refused_and_rolls_back(self, conference):
        session = make_session(conference)
        slot = place(session, length=15)
        session.duration_minutes = 0
        with pytest.raises(ValidationError) as excinfo:
            session.full_clean()
        assert "at least 15 minutes" in str(excinfo.value)
        with pytest.raises(ValidationError):
            session.save()
        session.refresh_from_db()
        slot.refresh_from_db()
        assert session.duration_minutes == 15
        assert slot.end_utc == T0 + timedelta(minutes=15)

    def test_a_slot_the_new_length_cannot_fit_keeps_the_old_length(self, conference):
        room = make_room(conference)
        session = make_session(conference)
        place(session, length=30, room=room)
        place(make_session(conference), minutes=30, room=room)
        session.duration_minutes = 45
        with pytest.raises(ValidationError):
            session.save()
        session.refresh_from_db()
        assert session.duration_minutes == 30

    def test_a_length_under_one_grid_step_is_refused(self, conference):
        SpeakerSettings.objects.update_or_create(
            conference=conference, defaults={"schedule_step_minutes": 5}
        )
        session = make_session(conference)
        place(session, length=15)
        session.duration_minutes = 4
        with pytest.raises(ValidationError) as excinfo:
            session.full_clean()
        assert "finer schedule grid step" in str(excinfo.value)
        session.duration_minutes = 5
        session.full_clean()

    def test_a_length_over_a_day_is_refused(self, conference):
        session = make_session(conference)
        place(session, length=15)
        session.duration_minutes = 24 * 60 + 1
        with pytest.raises(ValidationError) as excinfo:
            session.full_clean()
        assert "longer than a day" in str(excinfo.value)

    def test_an_unchanged_length_is_not_checked(self, conference):
        """A session whose slot already disagrees (data from before the two
        were kept together) still saves its other fields."""
        room = make_room(conference)
        session = make_session(conference)
        slot = place(session, length=15, room=room)
        place(make_session(conference), minutes=15, room=room)
        Session.objects.filter(pk=session.pk).update(duration_minutes=30)
        session.refresh_from_db()
        session.title = "Renamed"
        session.full_clean()
        session.save()
        slot.refresh_from_db()
        assert slot.end_utc == T0 + timedelta(minutes=15)

    def test_a_cancelled_session_and_its_record_slot_stay_apart(self, conference):
        room = make_room(conference)
        session = make_session(conference)
        slot = place(session, length=30, room=room)
        session.cancel()
        place(make_session(conference), minutes=30, room=room)
        session.duration_minutes = 60
        session.full_clean()
        session.save()
        slot.refresh_from_db()
        assert slot.end_utc == T0 + timedelta(minutes=30)
        slot.end_utc = T0 + timedelta(minutes=20)
        slot.save()
        session.refresh_from_db()
        assert session.duration_minutes == 60

    def test_a_resize_saves_the_session_so_its_signals_run(self, conference):
        """Session's post_save is what refreshes the public program's
        cache, so the length goes back through a save, not an update."""
        session = make_session(conference)
        slot = place(session, length=30)
        heard = []

        def spy(sender, instance, update_fields=None, **kwargs):
            heard.append((instance.pk, update_fields))

        post_save.connect(spy, sender=Session)
        try:
            slot.end_utc = T0 + timedelta(minutes=45)
            slot.save()
        finally:
            post_save.disconnect(spy, sender=Session)
        assert heard == [(session.pk, frozenset({"duration_minutes", "modified_date"}))]

    def test_a_status_change_does_not_look_up_the_slot(
        self, conference, django_assert_num_queries
    ):
        session = make_session(conference)
        place(session, length=30)
        with django_assert_num_queries(1):
            session.save(update_fields=["title"])

    def test_no_type_and_no_length_is_a_field_error(self, conference):
        """A form posted without a type reaches clean() with neither a
        length nor a type to take one from: the field error is the answer."""
        session = make_session(conference)
        place(session, length=15)
        session.kind = None
        session.duration_minutes = None
        with pytest.raises(ValidationError) as excinfo:
            session.full_clean()
        assert "kind" in excinfo.value.message_dict

    def test_saving_reads_no_stored_length_back(self, conference):
        """A loaded session remembers its stored length; a save that keeps
        it reads neither the session nor its slot again."""
        session = make_session(conference)
        place(session, length=90)
        session = Session.objects.get(pk=session.pk)
        session.title = "Renamed"
        with CaptureQueriesContext(connection) as queries:
            session.save()
        reads = [q["sql"] for q in queries if q["sql"].startswith("SELECT")]
        assert not any('FROM "speakers_scheduleslot"' in sql for sql in reads)
        assert not any(
            '"speakers_session"."duration_minutes" FROM' in sql for sql in reads
        )

    def test_a_deferred_length_is_read_when_saving(self, conference):
        session = make_session(conference)
        slot = place(session, length=90)
        deferred = Session.objects.defer("duration_minutes").get(pk=session.pk)
        deferred.duration_minutes = 30
        deferred.save()
        slot.refresh_from_db()
        assert slot.end_utc == T0 + timedelta(minutes=30)
        assert deferred.moved_slot == slot

    def test_a_length_read_on_demand_is_remembered(self, conference):
        session = make_session(conference)
        place(session, length=90)
        deferred = Session.objects.defer("duration_minutes").get(pk=session.pk)
        assert deferred.duration_minutes == 90
        assert deferred._stored_minutes == 90
        deferred.refresh_from_db(fields=["title"])
        assert deferred._stored_minutes == 90

    def test_a_slot_loaded_without_its_times_reads_them_back(self, conference):
        session = make_session(conference)
        place(session, length=90)
        slot = ScheduleSlot.objects.only("id", "session").get(session=session)
        slot.start_utc = T0
        slot.end_utc = T0 + timedelta(minutes=5)
        with pytest.raises(ValidationError, match="at least 15 minutes"):
            slot.save()

    def test_a_slot_with_no_stored_row_is_new(self, conference):
        session = make_session(conference)
        slot = ScheduleSlot(
            pk=987654,
            session=session,
            start_utc=T0,
            end_utc=T0 + timedelta(minutes=5),
        )
        with pytest.raises(ValidationError, match="at least 15 minutes"):
            slot.save()


@pytest.mark.django_db
class TestLengthsFromSlots:
    """The one-time reconciliation: where a session and its slot already
    disagree, the slot's length wins."""

    def test_the_slot_wins_and_cancelled_sessions_are_left(
        self, conference, other_conference, django_capture_on_commit_callbacks
    ):
        room = make_room(conference)
        placed = make_session(conference)
        place(placed, length=15, room=room)
        cancelled = make_session(conference)
        place(cancelled, minutes=30, length=15, room=room)
        cancelled.cancel()
        agreeing = make_session(conference)
        place(agreeing, minutes=60, length=20, room=room)
        Session.objects.filter(pk__in=[placed.pk, cancelled.pk]).update(
            duration_minutes=4
        )
        # The migration's own copy of the key must be the API's.
        generation = api._generation_key(conference.pk)
        untouched = api._generation_key(other_conference.pk)
        before = cache.get(generation, 0)
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            step_migration.lengths_from_slots(apps, None)
            # Not before the commit, so no request re-caches old lengths.
            assert cache.get(generation, 0) == before
        # The public API's cached responses go, as a save would clear them,
        # for the edition whose lengths changed only.
        assert len(callbacks) == 1
        assert cache.get(generation) == before + 1
        assert cache.get(untouched) is None
        lengths = dict(Session.objects.values_list("pk", "duration_minutes"))
        assert lengths[placed.pk] == 15
        assert lengths[cancelled.pk] == 4
        assert lengths[agreeing.pk] == 20
