"""Building the schedule editor's grid (design §10, task 4.2).

Rooms across, the edition's grid step down (15 minutes unless an
organizer picks another in the speaker settings), one day at a time. A
day is the event's own (midnight to midnight in its timezone), so an
evening social stays on its day; every moment is stored and sent as
UTC, and the browser labels the times in whatever timezone the organizer
picks, the event's by default (``static/js/schedule-editor.js`` reads
the ``data-utc`` attributes this module's cards carry).
"""

from datetime import datetime, timedelta, timezone

from django.db import transaction
from django.db.models import Q
from django.utils import timezone as dj_timezone

from .clock import today
from .constants import DEFAULT_SCHEDULE_STEP, OFF_SCHEDULE_STATUSES, SessionStatus
from .models import (
    ActivityLog,
    ChecklistItem,
    Presenter,
    PublishedSlot,
    Room,
    ScheduleSlot,
    Session,
    SessionPresenter,
    SpeakerSettings,
    event_tz,
)
from .readiness import refresh_readiness
from .tasks import send_schedule_update_task

# A slot shorter than this shows its title only, whatever the step: the
# times and the type are in its tooltip and behind its pencil.
BRIEF_MINUTES = 10

# The grid's first two columns: the hour gutter and the all-rooms lane
# where the opening and the breaks go. Rooms start in the third.
GUTTER_COLUMN = 1
ALL_ROOMS_COLUMN = 2
FIRST_ROOM_COLUMN = 3

# The header row is row 1; the day's first step is row 2.
FIRST_TIME_ROW = 2


def schedule_days(conference):
    """The dates the editor offers as tabs.

    The edition's listed event dates when it has any (a year of meetup
    nights), else its own span, plus any date a slot already sits on, so
    nothing scheduled can become unreachable. With none of these, today,
    so an empty editor still renders a grid.
    """
    days = {
        moment.date()
        for moment in ScheduleSlot.objects.filter(conference=conference).datetimes(
            "start_utc", "day", tzinfo=event_tz(conference)
        )
    }
    listed = set(conference.event_dates.values_list("date", flat=True))
    if listed:
        days |= listed
    elif conference.start_date and conference.end_date:
        day = conference.start_date
        while day <= conference.end_date:
            days.add(day)
            day += timedelta(days=1)
    elif conference.conference_date:
        days.add(conference.conference_date)
    if not days:
        days.add(today())
    return sorted(days)


def day_bounds(day, tz=timezone.utc):
    """Midnight to midnight in ``tz``, as UTC moments. The next midnight is
    computed on its own date, so a day that changes clocks is 23 or 25
    hours long rather than spilling into the next."""
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    following = day + timedelta(days=1)
    end = datetime(following.year, following.month, following.day, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def step_minutes(conference):
    """The edition's grid step, in minutes; the default without settings."""
    return SpeakerSettings.step_for(conference.pk)


def slots_between_rows(conference, step):
    """The edition's placed slots whose start falls between two rows of a
    ``step`` grid, in the event's time zone, earliest first. The grid
    draws such a slot in the row above, where it can share a cell with
    the slot before it, as after a switch from 5 minutes to 15."""
    tz = event_tz(conference)
    slots = (
        ScheduleSlot.objects.filter(conference=conference)
        .exclude(session__status__in=OFF_SCHEDULE_STATUSES)
        .select_related("session")
        .order_by("start_utc")
    )
    off = []
    for slot in slots:
        local = slot.start_utc.astimezone(tz)
        if (local.hour * 60 + local.minute) % step:
            off.append(slot)
    return off


def off_grid_warning(conference, step):
    """What an organizer is told after picking a step that some slots do
    not start on; None when every slot fits."""
    off = slots_between_rows(conference, step)
    if not off:
        return None
    tz = event_tz(conference)
    named = ", ".join(
        f"“{slot.session.title}” ({slot.start_utc.astimezone(tz):%H:%M})"
        for slot in off[:3]
    )
    if len(off) > 3:
        named += f" and {len(off) - 3} more"
    if len(off) == 1:
        count, verb, them = "1 slot starts", "is", "it"
    else:
        count, verb, them = f"{len(off)} slots start", "are", "them"
    return (
        f"{count} between two rows of the new {step}-minute grid and {verb} "
        f"drawn in the row above: {named}. Move {them} onto the grid, or "
        "pick a finer step."
    )


def row_scale(step):
    """How much taller than a quarter-hour row one row of ``step`` is.

    A step finer than a quarter hour keeps the quarter-hour row height,
    so even a one-minute card has room for its title; a coarser one
    grows, so an hour stays as tall as it was. Formatted for an inline
    style, never through the locale's decimal separator.
    """
    return f"{max(step, DEFAULT_SCHEDULE_STEP) / DEFAULT_SCHEDULE_STEP:g}"


def _row_of(moment, window_start, row_count, step):
    """The grid row a UTC moment falls in, clamped to the window."""
    offset = (moment - window_start).total_seconds() // (step * 60)
    return FIRST_TIME_ROW + int(max(0, min(row_count, offset)))


def _hour_of(moment, day_start):
    """The start of the hour a moment falls in, counted in whole hours
    from the day's local midnight. Every row time derives from the
    window's start, so a stray second here would shift the whole grid;
    and a UTC hour is not an event hour where the zone is offset by a
    half or a quarter hour (India, Nepal), which would put every row of
    a coarse step on the wrong minute."""
    hours = (moment - day_start) // timedelta(hours=1)
    return day_start + timedelta(hours=hours)


def _window(day_start, day_end, slots, full_day):
    """The hours the grid renders: the program plus an hour each side.

    A conference day occupies a fraction of its hours; the
    page shows the part that matters (design §10.2) unless asked for the
    whole day, or when there is nothing placed yet to trim around.
    """
    if full_day or not slots:
        return day_start, day_end
    first = max(min(slot.start_utc for slot in slots), day_start)
    last = min(max(slot.end_utc for slot in slots), day_end)
    start = max(day_start, _hour_of(first, day_start) - timedelta(hours=1))
    end = _hour_of(last, day_start) + timedelta(hours=1)
    if last != _hour_of(last, day_start):
        end += timedelta(hours=1)
    end = min(end, day_end)
    # A trim that saves less than two hours is a no-op with a toggle
    # link attached; show the whole day instead.
    if (start - day_start) + (day_end - end) < timedelta(hours=2):
        return day_start, day_end
    return start, end


def grid_for_day(conference, day, full_day=False, step=None):
    """Everything the grid template needs for one day, in flat queries.

    ``step`` is the edition's grid step, read from its settings when not
    given (the all-days view reads it once for every day).
    """
    if step is None:
        step = step_minutes(conference)
    hour_rows = 60 // step
    day_start, day_end = day_bounds(day, event_tz(conference))
    # The day's lanes are the rooms of its venue, plus the rooms without
    # one (online). A day with no venue shows every room.
    venue = conference.venue_for(day)
    rooms = Room.objects.filter(conference=conference, is_active=True).select_related(
        "venue"
    )
    if venue:
        rooms = rooms.filter(Q(venue=None) | Q(venue=venue))
    rooms = list(rooms)
    slots = list(
        ScheduleSlot.objects.filter(
            conference=conference, start_utc__lt=day_end, end_utc__gt=day_start
        )
        .exclude(session__status__in=OFF_SCHEDULE_STATUSES)
        .select_related("session__kind", "room__venue")
        .order_by("start_utc")
    )
    # A deactivated room that still holds a slot stays a lane, marked
    # retired, rather than its card being misdrawn in the all-rooms lane;
    # so does a room at another venue whose slot sits on this day.
    known = {room.pk for room in rooms}
    for slot in slots:
        if slot.room_id and slot.room_id not in known:
            known.add(slot.room_id)
            rooms.append(slot.room)
    # Each lane names its venue, so two venues' "Ballroom A" read apart.
    lanes = [
        {
            "pk": "",
            "name": "All rooms",
            "venue": venue.name if venue else "",
            "column": ALL_ROOMS_COLUMN,
        }
    ] + [
        {
            "pk": room.pk,
            "name": room.name if room.is_active else f"{room.name} (retired)",
            "venue": room.venue_label,
            "column": FIRST_ROOM_COLUMN + i,
        }
        for i, room in enumerate(rooms)
    ]
    last_column = FIRST_ROOM_COLUMN + len(rooms)
    window_start, window_end = _window(day_start, day_end, slots, full_day)
    row_count = int((window_end - window_start).total_seconds() // (step * 60))
    warnings = presenter_warnings(slots)
    published = {
        row.session_id: row
        for row in PublishedSlot.objects.filter(conference=conference)
    }
    column = {room.pk: FIRST_ROOM_COLUMN + i for i, room in enumerate(rooms)}
    cards = []
    for slot in slots:
        row = _row_of(slot.start_utc, window_start, row_count, step)
        span = max(1, _row_of(slot.end_utc, window_start, row_count, step) - row)
        minutes = int((slot.end_utc - slot.start_utc).total_seconds() // 60)
        if slot.room_id is None:
            start_column, end_column = ALL_ROOMS_COLUMN, last_column
        else:
            start_column = column[slot.room_id]
            end_column = start_column + 1
        cards.append(
            {
                "slot": slot,
                "session": slot.session,
                "row": row,
                "span": span,
                "start_column": start_column,
                "end_column": end_column,
                "is_band": slot.room_id is None,
                "minutes": minutes,
                # Title only, on one clipped line: a card less than two
                # quarter-hour rows tall, or a slot under ten minutes
                # however many fine rows it spans.
                "is_tight": span * max(step, DEFAULT_SCHEDULE_STEP)
                < 2 * DEFAULT_SCHEDULE_STEP
                or minutes < BRIEF_MINUTES,
                # Only what a publish would carry is "unpublished"; a
                # DRAFT or INVITED card is pencilled in and waits for
                # its confirmation instead (review of #461).
                "is_pencilled": slot.session.status not in PUBLISHABLE_STATUSES,
                "is_dirty": slot.session.status in PUBLISHABLE_STATUSES
                and (
                    slot.session_id not in published
                    or not published[slot.session_id].matches(slot)
                ),
                "warnings": warnings.get(slot.pk, []),
            }
        )
    rows = [
        {
            "index": FIRST_TIME_ROW + i,
            "utc": window_start + timedelta(minutes=step * i),
            "is_hour": i % hour_rows == 0,
        }
        for i in range(row_count)
    ]
    return {
        "trimmed": (window_start, window_end) != (day_start, day_end),
        "has_slots": bool(slots),
        "rooms": rooms,
        "lanes": lanes,
        "last_column": last_column,
        "rows": rows,
        "cards": cards,
        "day_start": day_start,
        "step_minutes": step,
        "hour_rows": hour_rows,
        "row_scale": row_scale(step),
    }


def also_in(presenter, session):
    """The double-booking warning line, one wording everywhere."""
    return f"{presenter.display_name} is also in “{session.title}”"


def presenter_warnings(slots):
    """``{slot.pk: ["Ada Lovelace is also in “X”", ...]}`` for one day.

    The double-booking warning of design §8.5, computed over the day's
    slots in one query instead of one ``presenter_clashes()`` call per
    slot, so the grid's query count stays flat.
    """
    links = SessionPresenter.objects.filter(
        session_id__in={slot.session_id for slot in slots}
    ).select_related("presenter")
    people = {}
    for link in links:
        people.setdefault(link.session_id, []).append(link.presenter)
    warnings = {}
    for slot in slots:
        for other in slots:
            if other.pk == slot.pk:
                continue
            if other.start_utc >= slot.end_utc or other.end_utc <= slot.start_utc:
                continue
            shared = [
                presenter
                for presenter in people.get(slot.session_id, [])
                if presenter in people.get(other.session_id, [])
            ]
            for presenter in shared:
                warnings.setdefault(slot.pk, []).append(
                    also_in(presenter, other.session)
                )
    return warnings


def presenter_schedule(conference, presenter):
    """The schedule as one presenter may see it, by their local day.

    Reads the published schedule only (§10.1): the working grid is the
    organizers' draft. Public sessions and program items (the keynote, the
    breaks, the social), plus the presenter's own; an
    entry of their own that is not on the public site yet carries a
    draft flag for the "not yet public" badge (design §2.4). Times are
    pre-formatted in the presenter's timezone, so the template never
    re-converts them (Django's date filter would pull aware datetimes
    back to UTC).
    """
    mine = set(
        SessionPresenter.objects.filter(presenter=presenter).values_list(
            "session_id", flat=True
        )
    )
    # A DRAFT or INVITED link means nobody has asked them yet: a
    # pencilled-in speaker is not told through their schedule page
    # (review of #460), so their own sessions appear from CONFIRMED on.
    slots = (
        PublishedSlot.objects.filter(conference=conference)
        .exclude(session__status__in=OFF_SCHEDULE_STATUSES)
        .filter(
            Q(session__is_public=True)
            | Q(session__kind__is_content=False)
            | (
                Q(session_id__in=mine)
                & Q(
                    session__status__in=(
                        SessionStatus.CONFIRMED,
                        SessionStatus.SCHEDULED,
                        SessionStatus.PUBLISHED,
                    )
                )
            )
        )
        .select_related("session__kind", "room__venue")
        .order_by("start_utc")
    )
    tz = presenter.tzinfo
    now = dj_timezone.now()
    days = []
    for slot in slots:
        start = slot.start_utc.astimezone(tz)
        minutes = int((slot.end_utc - slot.start_utc).total_seconds() // 60)
        entry = {
            "session": slot.session,
            "room": slot.room,
            "start_label": start.strftime("%H:%M"),
            "end_label": slot.end_utc.astimezone(tz).strftime("%H:%M"),
            "duration": f"{minutes} min",
            "is_mine": slot.session_id in mine,
            "is_draft": not slot.session.goes_public,
            # On stage right now: the card inverts to Night with a live tag.
            "is_live": slot.start_utc <= now < slot.end_utc,
        }
        if days and days[-1]["day"] == start.date():
            days[-1]["entries"].append(entry)
        else:
            days.append({"day": start.date(), "entries": [entry]})
    return days


# What a publish may carry to the speakers: sessions somebody said yes
# to. A DRAFT or INVITED session on the grid is the organizers' pencil,
# and publishing it would email people who may never have been asked
# (review of #461).
PUBLISHABLE_STATUSES = (
    SessionStatus.CONFIRMED,
    SessionStatus.SCHEDULED,
    SessionStatus.PUBLISHED,
)


def schedule_changes(conference):
    """The diff between the working grid and the published schedule.

    ``placed`` and ``moved`` hold working slots, ``removed`` the published
    rows whose session left the grid or stopped being publishable (a
    cancelled session's published row is removed on the next publish; so
    is anything that somehow regressed below CONFIRMED).
    """
    working = {
        slot.session_id: slot
        for slot in ScheduleSlot.objects.filter(
            conference=conference, session__status__in=PUBLISHABLE_STATUSES
        ).select_related("session", "room")
    }
    published = {
        row.session_id: row
        for row in PublishedSlot.objects.filter(conference=conference).select_related(
            "session", "room"
        )
    }
    placed = [slot for key, slot in working.items() if key not in published]
    moved = [
        slot
        for key, slot in working.items()
        if key in published and not published[key].matches(slot)
    ]
    removed = [row for key, row in published.items() if key not in working]
    return {"placed": placed, "moved": moved, "removed": removed}


def publish_schedule(conference, actor, notify=True):
    """Snapshot the working grid for the speakers (design §10.1).

    One whole-edition action, one transaction: this is the moment a
    session becomes SCHEDULED, its identity locks, its checklist lines
    open, and the feeds' SEQUENCE moves. With ``notify``, one email per
    affected presenter is queued on commit. Returns the change counts
    plus how many presenters were told.
    """
    now = dj_timezone.now()
    with transaction.atomic():
        changes = schedule_changes(conference)
        # One read for every row a move will touch: save() re-reads the
        # session for its conference otherwise, which made a publish
        # cost extra queries per moved session (review of #461).
        published = {
            row.session_id: row
            for row in PublishedSlot.objects.filter(
                conference=conference
            ).select_related("session")
        }
        affected = []
        for slot in changes["placed"]:
            PublishedSlot.objects.create(
                session=slot.session,
                room=slot.room,
                start_utc=slot.start_utc,
                end_utc=slot.end_utc,
                published_at=now,
            )
            if slot.session.status == SessionStatus.CONFIRMED:
                slot.session.schedule()
            ActivityLog.record(
                conference,
                "session.scheduled",
                target=slot.session,
                actor=actor,
                start=slot.start_utc.isoformat(),
            )
            affected.append((slot.session, "placed"))
        for slot in changes["moved"]:
            row = published[slot.session_id]
            row.room = slot.room
            row.start_utc = slot.start_utc
            row.end_utc = slot.end_utc
            row.published_at = now
            row.ics_sequence += 1
            row.save()
            ActivityLog.record(
                conference,
                "session.rescheduled",
                target=slot.session,
                actor=actor,
                start=slot.start_utc.isoformat(),
            )
            affected.append((slot.session, "moved"))
        for row in changes["removed"]:
            session = row.session
            row.delete()
            if session.status == SessionStatus.SCHEDULED:
                session.unschedule()
            ActivityLog.record(
                conference, "session.unscheduled", target=session, actor=actor
            )
            affected.append((session, "removed"))
        refresh_readiness(
            ChecklistItem.objects.filter(
                session__in=[session.pk for session, _ in affected]
            )
        )
        ActivityLog.record(
            conference,
            "schedule.published",
            actor=actor,
            placed=len(changes["placed"]),
            moved=len(changes["moved"]),
            removed=len(changes["removed"]),
            emailed=notify,
        )
        told = 0
        if notify and affected:
            by_presenter = {}
            links = SessionPresenter.objects.filter(
                session__in=[session.pk for session, _ in affected],
                confirmed_at__isnull=False,
            ).values_list("presenter_id", "session_id")
            change_of = {session.pk: change for session, change in affected}
            for presenter_id, session_id in links:
                by_presenter.setdefault(presenter_id, []).append(
                    [session_id, change_of[session_id]]
                )
            told = len(by_presenter)
            stamp = now.isoformat()
            for presenter_id, rows in by_presenter.items():
                transaction.on_commit(
                    lambda p=presenter_id, r=rows: (
                        send_schedule_update_task.delay(p, r, stamp)
                    )
                )
    return {
        "placed": len(changes["placed"]),
        "moved": len(changes["moved"]),
        "removed": len(changes["removed"]),
        "told": told,
    }


def unscheduled_sessions(conference):
    """The sidebar: everything placeable that has no slot yet."""
    return (
        Session.objects.for_conference(conference)
        .filter(slot__isnull=True)
        .exclude(status__in=OFF_SCHEDULE_STATUSES)
        .select_related("kind")
        .order_by("kind__sort_order", "title")
    )


def timezone_options(conference):
    """What the timezone switcher offers besides the browser's own zone.

    UTC, the organizers' display timezone, and each distinct timezone of a
    presenter on a scheduled session, labelled with a name, which is how
    "we scheduled her at 3 a.m." gets caught (design §10).
    """
    options = [("UTC", "UTC")]
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    if settings_row and settings_row.conference_timezone != "UTC":
        options.append(
            (settings_row.conference_timezone, settings_row.conference_timezone)
        )
    seen = {value for value, _ in options}
    presenters = (
        Presenter.objects.filter(
            conference=conference, session_presenters__session__slot__isnull=False
        )
        .distinct()
        .order_by("display_name")
    )
    for presenter in presenters:
        if presenter.timezone and presenter.timezone not in seen:
            seen.add(presenter.timezone)
            options.append(
                (
                    presenter.timezone,
                    f"{presenter.timezone} ({presenter.display_name})",
                )
            )
    return options
