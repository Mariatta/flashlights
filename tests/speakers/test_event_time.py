"""Organizers schedule in the event's own time: the editor's days run
midnight to midnight there, the keyboard form's start is local, and the
publishing page and the widget's default read the same way in person."""

import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from speakers.api import conference_block
from speakers.constants import EventFormat, SessionStatus
from speakers.schedule import day_bounds, event_tz, schedule_days

from .factories import make_published_slot, make_session, make_settings, make_slot

LA = "America/Los_Angeles"


@pytest.fixture
def long_beach(conference):
    conference.start_date = conference.end_date = date(2027, 5, 15)
    conference.save()
    return make_settings(
        conference, conference_timezone=LA, event_format=EventFormat.IN_PERSON
    )


@pytest.fixture
def organizer(db):
    return User.objects.create_user(username="org", is_staff=True)


class TestDayBounds:
    def test_midnight_to_midnight_in_the_zone(self):
        start, end = day_bounds(date(2027, 5, 15), ZoneInfo(LA))
        assert start == datetime(2027, 5, 15, 7, tzinfo=timezone.utc)
        assert end == datetime(2027, 5, 16, 7, tzinfo=timezone.utc)

    def test_a_clock_change_day_is_23_hours(self):
        start, end = day_bounds(date(2027, 3, 14), ZoneInfo(LA))
        assert (end - start).total_seconds() == 23 * 3600


@pytest.mark.django_db
class TestEditor:
    def test_an_evening_social_stays_on_its_day(self, conference, long_beach):
        social = make_session(conference, kind="SOCIAL", status=SessionStatus.CONFIRMED)
        # 17:30 in Long Beach is 00:30 UTC the next day.
        make_slot(social, start_utc=datetime(2027, 5, 16, 0, 30, tzinfo=timezone.utc))
        assert schedule_days(conference) == [date(2027, 5, 15)]
        assert str(event_tz(conference)) == LA

    def test_the_keyboard_form_sends_local_time(
        self, client, conference, long_beach, organizer
    ):
        talk = make_session(conference, kind="TALK", status=SessionStatus.CONFIRMED)
        client.force_login(organizer)
        response = client.patch(
            reverse("speakers:session_slot", args=[talk.slug]),
            json.dumps({"start": "2027-05-15T13:00:00", "duration": 30}),
            content_type="application/json",
        )
        assert response.status_code == 200, response.content
        talk.slot.refresh_from_db()
        assert talk.slot.start_utc == datetime(2027, 5, 15, 20, tzinfo=timezone.utc)

    def test_the_editor_defaults_to_the_events_zone(
        self, client, conference, long_beach, organizer
    ):
        client.force_login(organizer)
        page = client.get(reverse("speakers:schedule_editor")).content.decode()
        assert f'data-default="{LA}"' in page


@pytest.mark.django_db
class TestReadingIt:
    def test_publishing_lists_local_times(
        self, client, conference, long_beach, organizer
    ):
        talk = make_session(conference, kind="TALK", status=SessionStatus.CONFIRMED)
        make_slot(talk, start_utc=datetime(2027, 5, 15, 20, tzinfo=timezone.utc))
        make_published_slot(talk)
        talk.schedule()
        client.force_login(organizer)
        page = client.get(reverse("speakers:program_publishing")).content.decode()
        assert f"Sat 15 May, 13:00 {LA}" in page

    def test_the_api_says_in_person(self, conference, long_beach):
        assert conference_block(conference)["in_person"] is True
