"""Editions that meet on separate days: listed event dates, and rooms
tied to some of them."""

from datetime import date, datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from portal.models import Cadence, Conference, EventDate
from speakers.models import Room
from speakers.schedule import grid_for_day, schedule_days
from tests.grants import on_team

from .factories import make_room, make_session, make_settings, make_slot

FEB = date(2027, 2, 13)
MAR = date(2027, 3, 13)
MAY = date(2027, 5, 15)


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
        "cadence": "ONCE",
        "conference_date": "2027-05-01",
    }
    data.update(extra)
    return data


def rows(*items):
    """Formset data for the dates block. An item is (date, label), or
    (date, label, row) for an existing row, which may end with "delete".
    Existing rows come first, as the page posts them."""
    items = sorted(items, key=lambda item: len(item) < 3)
    data = {
        "dates-TOTAL_FORMS": str(len(items)),
        "dates-INITIAL_FORMS": str(sum(1 for item in items if len(item) > 2)),
        "dates-MIN_NUM_FORMS": "0",
        "dates-MAX_NUM_FORMS": "1000",
    }
    for i, item in enumerate(items):
        data[f"dates-{i}-date"] = item[0]
        data[f"dates-{i}-label"] = item[1]
        if len(item) > 2:
            data[f"dates-{i}-id"] = str(item[2].pk)
        if item[-1] == "delete":
            data[f"dates-{i}-DELETE"] = "on"
    return data


def series_data(conference, *items, **extra):
    return edition_data(conference, cadence="SERIES", **rows(*items), **extra)


def lanes(conference, day):
    return [lane["name"] for lane in grid_for_day(conference, day)["lanes"][1:]]


@pytest.mark.django_db
class TestEditionForm:
    def test_dates_are_listed_kept_and_dropped(self, client, admin_user, conference):
        client.force_login(admin_user)
        url = reverse("conference_edit", kwargs={"pk": conference.pk})
        client.post(
            url,
            series_data(conference, ("2027-03-13", ""), (FEB, "February workshop")),
        )
        assert [(d.date, d.label) for d in conference.event_dates.all()] == [
            (FEB, "February workshop"),
            (MAR, ""),
        ]
        # The edition's date and span follow the list.
        conference.refresh_from_db()
        assert conference.cadence == Cadence.SERIES
        assert (conference.conference_date, conference.start_date) == (FEB, FEB)
        assert conference.end_date == MAR
        feb = conference.event_dates.get(date=FEB)
        mar = conference.event_dates.get(date=MAR)
        room = make_room(conference, name="Improving")
        room.event_dates.add(feb)
        # The page shows the rows, and a blank one to add to.
        formset = client.get(url).context["formset"]
        assert [form.instance for form in formset.initial_forms] == [feb, mar]
        assert len(formset.extra_forms) == 1
        # A row edited in place keeps its id, and the room tied to it;
        # a removed row goes.
        client.post(
            url,
            series_data(conference, (FEB, "Workshop", feb), (MAR, "", mar, "delete")),
        )
        assert list(conference.event_dates.values_list("pk", "label")) == [
            (feb.pk, "Workshop")
        ]
        assert list(room.event_dates.all()) == [feb]
        conference.refresh_from_db()
        assert conference.end_date == FEB
        # Once a year lists nothing: the rows go, whatever was posted.
        client.post(url, edition_data(conference, **rows((FEB, "Workshop", feb))))
        assert not conference.event_dates.exists()
        conference.refresh_from_db()
        assert conference.cadence == Cadence.ONCE
        assert str(conference.conference_date) == "2027-05-01"

    @pytest.mark.parametrize(
        "items, error",
        [
            ((("13/02/2027", ""),), "Enter a valid date"),
            (((FEB, ""), (FEB, "again")), "duplicate data"),
            ((), "List at least one date"),
            ((("", "a label without a date"),), "This field is required"),
        ],
    )
    def test_bad_rows_are_refused(self, client, admin_user, conference, items, error):
        client.force_login(admin_user)
        response = client.post(
            reverse("conference_edit", kwargs={"pk": conference.pk}),
            series_data(conference, *items),
        )
        assert error in response.content.decode()
        assert not conference.event_dates.exists()

    def test_once_a_year_needs_its_date(self, client, admin_user, conference):
        client.force_login(admin_user)
        url = reverse("conference_edit", kwargs={"pk": conference.pk})
        response = client.post(url, edition_data(conference, conference_date=""))
        assert "When does it happen?" in response.content.decode()
        response = client.post(
            url, edition_data(conference, conference_date="2027-05-02", end_date=MAR)
        )
        assert "The last day is before the event date." in response.content.decode()
        # The last day is optional; the start date mirrors the event date.
        client.post(url, edition_data(conference, conference_date="2027-05-02"))
        conference.refresh_from_db()
        assert str(conference.start_date) == "2027-05-02"
        assert str(conference.end_date) == "2027-05-02"
        client.post(
            url, edition_data(conference, conference_date="2027-05-02", end_date=MAY)
        )
        conference.refresh_from_db()
        assert (conference.start_date, conference.end_date) == (date(2027, 5, 2), MAY)

    def test_the_form_asks_which_kind_first(self, client, admin_user, conference):
        client.force_login(admin_user)
        content = client.get(
            reverse("conference_edit", kwargs={"pk": conference.pk})
        ).content.decode()
        assert "What kind of event" in content
        assert 'data-show-when="id_cadence=ONCE"' in content
        assert 'data-show-when="id_cadence=SERIES"' in content
        assert "js/show-when" in content
        assert "id_start_date" not in content
        # The dates come as rows added one at a time.
        assert "data-formset-add" in content and "js/formset-rows" in content
        assert 'name="dates-__prefix__-date"' in content

    def test_the_list_counts_a_series_dates(self, client, admin_user, conference):
        client.force_login(admin_user)
        conference.cadence = Cadence.SERIES
        conference.save()
        conference.event_dates.create(date=FEB)
        conference.event_dates.create(date=MAR)
        conference.span_from_dates()
        content = client.get(reverse("conference_list")).content.decode()
        assert "2 dates" in content
        assert "13 Feb to 13 Mar 2027" in content

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
class TestStartNextYear:
    def start(self, client, admin_user, **data):
        client.force_login(admin_user)
        return client.post(
            reverse("start_new_year"),
            {"year": 2027, "name": "Next", "slug": "2027", **data},
        )

    def test_once_a_year(self, client, admin_user, conference):
        response = self.start(client, admin_user, cadence="ONCE")
        assert "When does it happen?" in response.content.decode()
        self.start(client, admin_user, cadence="ONCE", conference_date="2027-05-01")
        new = Conference.objects.get(year=2027)
        assert new.cadence == Cadence.ONCE
        assert str(new.start_date) == "2027-05-01"
        assert str(new.end_date) == "2027-05-01"

    def test_a_series(self, client, admin_user, conference):
        response = self.start(client, admin_user, cadence="SERIES")
        assert "List at least one date" in response.content.decode()
        response = self.start(
            client, admin_user, cadence="SERIES", **rows((FEB, ""), (FEB, "again"))
        )
        assert "duplicate data" in response.content.decode()
        assert not Conference.objects.filter(year=2027).exists()
        self.start(
            client,
            admin_user,
            cadence="SERIES",
            **rows(("2027-03-13", ""), (FEB, "February workshop")),
        )
        new = Conference.objects.get(year=2027)
        assert new.cadence == Cadence.SERIES
        assert list(new.event_dates.values_list("date", flat=True)) == [FEB, MAR]
        assert (new.conference_date, new.start_date, new.end_date) == (FEB, FEB, MAR)

    def test_the_form_asks_which_kind_first(self, client, admin_user, conference):
        client.force_login(admin_user)
        content = client.get(reverse("start_new_year")).content.decode()
        assert "What kind of event" in content
        assert 'data-show-when="id_cadence=SERIES"' in content
        assert "id_start_date" not in content
        assert 'name="dates-__prefix__-date"' in content


@pytest.mark.django_db
def test_the_pages_say_events(client, admin_user, conference):
    assert reverse("conference_list") == "/events/"
    assert reverse("start_new_year") == "/events/start-next/"
    assert reverse("conference_edit", args=[conference.pk]).startswith("/events/")
    assert reverse("conference_tickets", args=[conference.pk]).startswith("/events/")


@pytest.mark.django_db
def test_span_from_nothing_changes_nothing(conference):
    before = conference.conference_date
    conference.span_from_dates()
    conference.refresh_from_db()
    assert conference.conference_date == before and conference.start_date is None


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
