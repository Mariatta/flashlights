"""Due dates in a series count from the speaker's own date, and follow
the slot when it moves."""

from datetime import date, datetime, timezone

import pytest

from portal.models import Cadence
from speakers.checklists import (
    apply_template_item_changes,
    instantiate_general_checklist,
    instantiate_presenter_checklist,
    reanchor_session,
)
from speakers.constants import DueAnchor, NoticeKind
from speakers.seeds import seed_checklists

from .factories import (
    add_presenter,
    make_presenter,
    make_session,
    make_settings,
    make_slot,
)

# 13 Mar 2027 at 7 pm in Vancouver is already 14 Mar in UTC.
MARCH_NIGHT = datetime(2027, 3, 14, 2, 0, tzinfo=timezone.utc)
MAY_NIGHT = datetime(2027, 5, 16, 2, 0, tzinfo=timezone.utc)


@pytest.fixture
def series(conference):
    conference.cadence = Cadence.SERIES
    conference.start_date = conference.conference_date = date(2027, 2, 13)
    conference.save()
    make_settings(conference, conference_timezone="America/Vancouver")
    seed_checklists(conference)
    return conference


def confirmed(session, presenter):
    link = add_presenter(session, presenter, confirmed=True)
    instantiate_presenter_checklist(link)
    instantiate_general_checklist(presenter)
    return link


def before_event(presenter, session=None):
    """The presenter's items whose line counts from the event start."""
    return presenter.checklist_items.filter(
        template_item__due_anchor=DueAnchor.CONFERENCE_START, session=session
    ).select_related("template_item")


def due(items):
    return {item.title: item.due_date for item in items}


def expected(items, day):
    return {
        item.title: date.fromordinal(
            day.toordinal() - item.template_item.due_offset_days
        )
        for item in items
    }


@pytest.mark.django_db
class TestSeriesAnchors:
    def test_a_session_item_counts_from_its_night(self, series):
        session = make_session(series, kind="WORKSHOP")
        link = confirmed(session, make_presenter(series))
        items = before_event(link.presenter, session)
        assert items and all(item.due_date is None for item in items)
        # Scheduled: the due dates count from the night, in the event's day.
        slot = make_slot(session, start_utc=MARCH_NIGHT)
        assert due(before_event(link.presenter, session)) == expected(
            items, date(2027, 3, 13)
        )
        item = before_event(link.presenter, session).first()
        assert item.pending_notice == NoticeKind.CHANGED
        # Moved: they follow. Taken off: the dates stand.
        slot.start_utc = MAY_NIGHT
        slot.end_utc = None
        slot.save()
        assert due(before_event(link.presenter, session)) == expected(
            items, date(2027, 5, 15)
        )
        slot.delete()
        assert due(before_event(link.presenter, session)) == expected(
            items, date(2027, 5, 15)
        )

    def test_a_once_per_presenter_item_counts_from_their_first_night(self, series):
        presenter = make_presenter(series)
        first = make_session(series, kind="WORKSHOP")
        second = make_session(series, kind="WORKSHOP")
        confirmed(first, presenter)
        confirmed(second, presenter)
        general = before_event(presenter)
        assert general and all(item.due_date is None for item in general)
        make_slot(second, start_utc=MAY_NIGHT)
        assert due(before_event(presenter)) == expected(general, date(2027, 5, 15))
        make_slot(first, start_utc=MARCH_NIGHT)
        assert due(before_event(presenter)) == expected(general, date(2027, 3, 13))

    def test_editing_the_line_keeps_the_rule(self, series):
        session = make_session(series, kind="WORKSHOP")
        link = confirmed(session, make_presenter(series))
        make_slot(session, start_utc=MARCH_NIGHT)
        item = before_event(link.presenter, session).first()
        line = item.template_item
        line.due_offset_days = 2
        line.save()
        apply_template_item_changes(line)
        item.refresh_from_db()
        assert item.due_date == date(2027, 3, 11)

    def test_nothing_to_do_without_anchored_items(self, series):
        session = make_session(series, kind="WORKSHOP")
        assert reanchor_session(session) == 0


@pytest.mark.django_db
class TestOnceAYear:
    def test_the_event_start_stays_the_anchor(self, conference):
        conference.start_date = date(2026, 12, 5)
        conference.save()
        make_settings(conference, conference_timezone="America/Vancouver")
        seed_checklists(conference)
        session = make_session(conference, kind="WORKSHOP")
        link = confirmed(session, make_presenter(conference))
        items = before_event(link.presenter, session)
        assert due(items) == expected(items, date(2026, 12, 5))
        make_slot(session, start_utc=MARCH_NIGHT)
        assert due(before_event(link.presenter, session)) == expected(
            items, date(2026, 12, 5)
        )

    def test_before_the_session_follows_the_slot_in_the_events_day(self, conference):
        make_settings(conference, conference_timezone="America/Vancouver")
        seed_checklists(conference)
        session = make_session(conference, kind="WORKSHOP")
        link = confirmed(session, make_presenter(conference))
        item = link.presenter.checklist_items.filter(
            session=session, template_item__due_anchor=DueAnchor.SESSION_START
        ).first()
        line = item.template_item
        assert item.due_date is None
        make_slot(session, start_utc=MARCH_NIGHT)
        item.refresh_from_db()
        assert item.due_date == date.fromordinal(
            date(2027, 3, 13).toordinal() - line.due_offset_days
        )
