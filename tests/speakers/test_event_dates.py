"""Editions that meet on separate days: listed event dates, and rooms
tied to some of them."""

from datetime import date, datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from portal.models import Conference, EventDate
from speakers.models import Room
from speakers.schedule import grid_for_day, schedule_days
from tests.grants import on_team

from .factories import make_room, make_session, make_settings, make_slot

FEB = date(2027, 2, 13)
MAR = date(2027, 3, 13)


@pytest.fixture
def enabled(conference):
    return make_settings(conference)


@pytest.fixture
def organizer(db):
    return on_team(User.objects.create_user(username="org", email="org@x.org"))


def edition_data(conference, **extra):
    data = {
        "year": conference.year,
        "name": conference.name,
        "slug": conference.slug,
        "sponsorship_goal": "0",
        "donation_goal": "0",
        "proposals_count": "0",
        "chat_platform": "NONE",
    }
    data.update(extra)
    return data


def lanes(conference, day):
    return [lane["name"] for lane in grid_for_day(conference, day)["lanes"][1:]]


@pytest.mark.django_db
class TestEditionForm:
    def test_dates_are_listed_kept_and_dropped(self, client, admin_user, conference):
        client.force_login(admin_user)
        url = reverse("conference_edit", kwargs={"pk": conference.pk})
        client.post(
            url,
            edition_data(
                conference,
                event_dates="2027-03-13\n\n2027-02-13 February workshop\n",
            ),
        )
        assert [(d.date, d.label) for d in conference.event_dates.all()] == [
            (FEB, "February workshop"),
            (MAR, ""),
        ]
        feb = conference.event_dates.get(date=FEB)
        room = make_room(conference, name="Improving")
        room.event_dates.add(feb)
        form = client.get(url).context["form"]
        assert form["event_dates"].value() == "2027-02-13 February workshop\n2027-03-13"
        # A date still listed keeps its row, and the room tied to it.
        client.post(url, edition_data(conference, event_dates="2027-02-13 Workshop"))
        assert list(conference.event_dates.values_list("date", "label")) == [
            (FEB, "Workshop")
        ]
        assert list(room.event_dates.all()) == [feb]
        client.post(url, edition_data(conference, event_dates=""))
        assert not conference.event_dates.exists()

    @pytest.mark.parametrize(
        "lines, error",
        [
            ("13/02/2027", "is not a date"),
            ("2027-02-13\n2027-02-13 again", "listed twice"),
            ("2026-12-31", "outside the start and end dates"),
        ],
    )
    def test_bad_lines_are_refused(self, client, admin_user, conference, lines, error):
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            edition_data(
                conference,
                start_date="2027-01-01",
                end_date="2027-12-31",
                event_dates=lines,
            ),
        )
        assert error in response.content.decode()
        assert not conference.event_dates.exists()

    def test_str(self, conference):
        row = EventDate(conference=conference, date=FEB)
        assert str(row) == "Sat 13 Feb 2027"
        row.label = "February workshop"
        assert str(row) == "Sat 13 Feb 2027, February workshop"


@pytest.mark.django_db
class TestScheduleDays:
    def test_listed_dates_replace_the_span(self, conference, enabled):
        conference.start_date = date(2027, 1, 1)
        conference.end_date = date(2027, 12, 31)
        conference.save()
        assert len(schedule_days(conference)) == 365
        conference.event_dates.create(date=MAR)
        conference.event_dates.create(date=FEB)
        assert schedule_days(conference) == [FEB, MAR]
        # A slot on another day keeps that day reachable.
        stray = datetime(2027, 4, 10, 18, 0, tzinfo=timezone.utc)
        make_slot(make_session(conference), start_utc=stray)
        assert schedule_days(conference) == [FEB, MAR, date(2027, 4, 10)]

    def test_the_editor_offers_the_listed_dates(
        self, client, organizer, enabled, conference
    ):
        conference.event_dates.create(date=FEB)
        client.force_login(organizer)
        response = client.get(reverse("speakers:schedule_editor"))
        assert response.context["days"] == [FEB]


@pytest.mark.django_db
class TestRoomsPerDate:
    def test_a_date_has_its_rooms_and_the_everyday_ones(self, conference, enabled):
        feb = conference.event_dates.create(date=FEB)
        mar = conference.event_dates.create(date=MAR)
        make_room(conference, name="Online")
        for name in ("Improving: main", "Improving: lab"):
            make_room(conference, name=name).event_dates.add(feb)
        make_room(conference, name="SAP").event_dates.add(mar, feb)
        assert lanes(conference, FEB) == [
            "Improving: lab",
            "Improving: main",
            "Online",
            "SAP",
        ]
        assert lanes(conference, MAR) == ["Online", "SAP"]

    def test_a_room_holding_a_slot_off_its_dates_keeps_its_lane(
        self, conference, enabled
    ):
        feb = conference.event_dates.create(date=FEB)
        conference.event_dates.create(date=MAR)
        room = make_room(conference, name="Improving")
        room.event_dates.add(feb)
        start = datetime(2027, 3, 14, 2, 0, tzinfo=timezone.utc)  # 13 Mar, Vancouver
        make_slot(make_session(conference), room=room, start_utc=start)
        enabled.conference_timezone = "America/Vancouver"
        enabled.save()
        assert lanes(conference, MAR) == ["Improving"]

    def test_the_room_form_offers_the_dates(self, client, organizer, conference):
        make_settings(conference)
        client.force_login(organizer)
        form = client.get(reverse("speakers:room_create")).context["form"]
        assert "event_dates" not in form.fields
        feb = conference.event_dates.create(date=FEB)
        other = EventDate.objects.create(
            conference=make_other_edition(), date=FEB + timedelta(days=1)
        )
        form = client.get(reverse("speakers:room_create")).context["form"]
        assert list(form.fields["event_dates"].queryset) == [feb]
        client.post(
            reverse("speakers:room_create"),
            {"name": "Improving", "kind": "ROOM", "event_dates": [feb.pk]},
        )
        room = Room.objects.get(name="Improving")
        assert list(room.event_dates.all()) == [feb]
        refused = client.post(
            reverse("speakers:room_create"),
            {"name": "Elsewhere", "kind": "ROOM", "event_dates": [other.pk]},
        )
        assert "event_dates" in refused.context["form"].errors
        make_room(conference, name="Online")
        listing = client.get(reverse("speakers:room_list")).content.decode()
        assert "13 Feb 2027" in listing
        assert "Every date" in listing


def make_other_edition():
    return Conference.objects.create(year=1999, name="Other", slug="other")


@pytest.mark.django_db
class TestLanding:
    def test_the_next_date_is_on_the_hero(self, client, conference):
        today = date.today()
        conference.event_dates.create(date=today - timedelta(days=7))
        upcoming = conference.event_dates.create(
            date=today + timedelta(days=7), label="Next meetup"
        )
        content = client.get(reverse("index")).content.decode()
        assert f"Next: {upcoming.date:%a} {upcoming.date.day} " in content
        assert "Next meetup" in content
        upcoming.delete()
        content = client.get(reverse("index")).content.decode()
        assert "Next:" not in content
