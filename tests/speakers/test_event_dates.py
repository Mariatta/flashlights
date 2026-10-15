"""Editions that meet on separate days: listed event dates, each with a
venue, and the schedule editor laning a day by its venue."""

from datetime import date, datetime, timedelta, timezone

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from portal.models import Cadence, Conference, EventDate, Venue
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


def make_series(conference, *days):
    conference.cadence = Cadence.SERIES
    conference.save()
    rows = [conference.event_dates.create(date=day) for day in days]
    conference.span_from_dates()
    return rows


def dates_url(conference):
    return reverse("conference_dates", kwargs={"pk": conference.pk})


def lanes(conference, day):
    return [lane["name"] for lane in grid_for_day(conference, day)["lanes"][1:]]


@pytest.mark.django_db
class TestEditionForm:
    def test_a_series_sends_you_to_its_dates(self, client, admin_user, conference):
        client.force_login(admin_user)
        url = reverse("conference_edit", kwargs={"pk": conference.pk})
        # Switched to a series with nothing listed: the Dates page is next.
        response = client.post(url, edition_data(conference, cadence="SERIES"))
        assert response.status_code == 302 and response.url == dates_url(conference)
        conference.refresh_from_db()
        assert conference.cadence == Cadence.SERIES
        assert "Now list the dates" in client.get(response.url).content.decode()
        # With dates listed the form summarises them and links there, and
        # a save keeps them and goes back to the list.
        feb, mar = make_series(conference, FEB, MAR)
        content = client.get(url).content.decode()
        assert "Sat 13 Feb 2027" in content and "Sat 13 Mar 2027" in content
        assert "Add or change the dates" in content and dates_url(conference) in content
        assert 'name="dates-' not in content
        response = client.post(url, edition_data(conference, cadence="SERIES"))
        assert response.url == reverse("conference_list")
        assert list(conference.event_dates.all()) == [feb, mar]
        conference.refresh_from_db()
        assert (conference.conference_date, conference.end_date) == (FEB, MAR)
        # Once a year lists nothing: the rows go.
        client.post(url, edition_data(conference))
        assert not conference.event_dates.exists()
        conference.refresh_from_db()
        assert conference.cadence == Cadence.ONCE
        assert str(conference.conference_date) == "2027-05-01"

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
        assert "Save, then list the dates on the Dates page." in content

    def test_the_tabs_under_the_event(self, client, admin_user, conference):
        client.force_login(admin_user)
        url = reverse("conference_edit", kwargs={"pk": conference.pk})
        content = client.get(url).content.decode()
        tickets = reverse("conference_tickets", kwargs={"pk": conference.pk})
        assert f'href="{url}">Event</a>' in content
        assert f'href="{tickets}">Tickets</a>' in content
        assert dates_url(conference) not in content  # once a year
        assert reverse("speakers:room_list") not in content  # program off
        make_series(conference, FEB)
        make_settings(conference)
        content = client.get(url).content.decode()
        assert f'href="{dates_url(conference)}">Dates</a>' in content
        assert f'href="{reverse("speakers:room_list")}">Rooms</a>' in content
        # The tickets page carries the same tabs.
        assert f'href="{url}">Event</a>' in client.get(tickets).content.decode()

    def test_the_list_counts_a_series_dates(self, client, admin_user, conference):
        client.force_login(admin_user)
        make_series(conference, FEB, MAR)
        conference.venue = Venue.objects.create(name="SAP")
        conference.save()
        content = client.get(reverse("conference_list")).content.decode()
        assert "2 dates" in content and dates_url(conference) in content
        assert "13 Feb to 13 Mar 2027" in content
        assert reverse("venue_edit", args=[conference.venue.pk]) in content

    def test_str(self, conference):
        row = EventDate(conference=conference, date=FEB)
        assert str(row) == "Sat 13 Feb 2027"
        row.label = "February workshop"
        assert str(row) == "Sat 13 Feb 2027, February workshop"


@pytest.mark.django_db
class TestDatesPage:
    def test_add_edit_and_remove(self, client, admin_user, conference):
        client.force_login(admin_user)
        make_series(conference)
        conference.venue = Venue.objects.create(name="SAP")
        conference.save()
        url = dates_url(conference)
        content = client.get(url).content.decode()
        assert "No dates listed yet." in content
        assert "The event&#x27;s venue, SAP" in content
        assert reverse("venue_create") in content
        # Added one at a time; a blank venue means the event's.
        client.post(url, {"date": "2027-03-13", "label": ""})
        response = client.post(
            url, {"date": "2027-02-13", "label": "February workshop"}, follow=True
        )
        assert "Added Sat 13 Feb 2027, February workshop." in response.content.decode()
        assert [(d.date, d.label, d.venue) for d in conference.event_dates.all()] == [
            (FEB, "February workshop", None),
            (MAR, "", None),
        ]
        content = response.content.decode()
        assert "February workshop" in content
        assert content.count("SAP") >= 3  # the rows say where, in grey
        # The edition's date and span follow the list.
        conference.refresh_from_db()
        assert (conference.conference_date, conference.end_date) == (FEB, MAR)
        # A date twice is refused.
        refused = client.post(url, {"date": "2027-02-13", "label": "again"})
        assert "This event already lists that date." in refused.content.decode()
        assert conference.event_dates.count() == 2
        # Edited in place, with a venue of its own, which gets a room.
        feb = conference.event_dates.get(date=FEB)
        annex = Venue.objects.create(name="Annex")
        edit = reverse(
            "conference_date_edit", kwargs={"pk": conference.pk, "date_pk": feb.pk}
        )
        assert "February workshop" in client.get(edit).content.decode()
        response = client.post(
            edit, {"date": "2027-02-14", "label": "Workshop", "venue": annex.pk}
        )
        assert response.url == url
        feb.refresh_from_db()
        assert (feb.date, feb.label, feb.venue) == (
            FEB + timedelta(days=1),
            "Workshop",
            annex,
        )
        assert Room.objects.filter(
            conference=conference, venue=annex, name="Annex"
        ).exists()
        assert "Annex" in client.get(url).content.decode()
        conference.refresh_from_db()
        assert conference.conference_date == FEB + timedelta(days=1)
        # Removed with the button; the span follows.
        remove = reverse(
            "conference_date_delete", kwargs={"pk": conference.pk, "date_pk": feb.pk}
        )
        assert client.get(remove).status_code == 405
        response = client.post(remove, follow=True)
        assert "Removed Sun 14 Feb 2027, Workshop." in response.content.decode()
        assert list(conference.event_dates.values_list("date", flat=True)) == [MAR]
        conference.refresh_from_db()
        assert conference.conference_date == MAR

    def test_bad_rows_are_refused(self, client, admin_user, conference):
        client.force_login(admin_user)
        make_series(conference)
        url = dates_url(conference)
        assert (
            "Enter a valid date"
            in client.post(url, {"date": "13/02/2027", "label": ""}).content.decode()
        )
        assert (
            "This field is required"
            in client.post(
                url, {"date": "", "label": "a label without a date"}
            ).content.decode()
        )
        other = Venue.objects.create(name="Other")
        assert (
            "Select a valid choice"
            in client.post(
                url, {"date": "2027-02-13", "venue": other.pk + 1}
            ).content.decode()
        )
        assert not conference.event_dates.exists()

    def test_once_a_year_has_its_date_on_the_form(self, client, admin_user, conference):
        client.force_login(admin_user)
        response = client.get(dates_url(conference), follow=True)
        assert response.redirect_chain[-1][0] == reverse(
            "conference_edit", kwargs={"pk": conference.pk}
        )
        assert "dates are on its edit page" in response.content.decode()

    def test_only_event_editors(self, client, portal_user, conference):
        make_series(conference, FEB)
        client.force_login(portal_user)
        assert client.get(dates_url(conference)).status_code in (302, 403)
        assert client.post(
            dates_url(conference), {"date": "2027-03-13"}
        ).status_code in (
            302,
            403,
        )
        assert conference.event_dates.count() == 1
        client.logout()
        assert client.get(dates_url(conference)).status_code == 302

    def test_the_venue_choice_without_an_event_venue(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        make_series(conference)
        content = client.get(dates_url(conference)).content.decode()
        assert "The event&#x27;s venue, when it picks one" in content
        conference.event_dates.create(date=FEB)
        assert "Online" in client.get(dates_url(conference)).content.decode()

    def test_the_dashboard_offers_dates_and_venues(
        self, client, admin_user, conference
    ):
        client.force_login(admin_user)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert "Add a venue" in content and "Add a date" not in content
        make_series(conference, FEB)
        content = client.get(reverse("organizer_dashboard")).content.decode()
        assert "Add a date" in content and dates_url(conference) in content


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
class TestLanesByVenue:
    def test_a_day_lanes_the_rooms_of_its_venue(self, conference, enabled):
        improving = Venue.objects.create(name="Improving")
        sap = Venue.objects.create(name="SAP")
        # Each date's venue gets its room; a venue-less room is everywhere.
        conference.event_dates.create(date=FEB, venue=improving)
        conference.event_dates.create(date=MAR, venue=sap)
        conference.event_dates.create(date=MAY)
        make_room(conference, name="Online")
        make_room(conference, name="Lab", venue=improving)
        make_room(conference, name="Ballroom A", venue=improving)
        make_room(conference, name="Ballroom A", venue=sap)
        assert lanes(conference, FEB) == ["Ballroom A", "Improving", "Lab", "Online"]
        assert lanes(conference, MAR) == ["Ballroom A", "Online", "SAP"]
        # A day with no venue, and no event venue, shows every room.
        assert lanes(conference, MAY) == [
            "Ballroom A",
            "Ballroom A",
            "Improving",
            "Lab",
            "Online",
            "SAP",
        ]
        # Each lane names its venue, the all-rooms lane the day's.
        grid = grid_for_day(conference, MAR)
        assert [(lane["name"], lane["venue"]) for lane in grid["lanes"]] == [
            ("All rooms", "SAP"),
            ("Ballroom A", "SAP"),
            ("Online", ""),
            ("SAP", ""),  # named after its venue: once is enough
        ]

    def test_the_event_venue_is_the_default(self, conference, enabled):
        conference.venue = Venue.objects.create(name="Convention Center")
        conference.save()  # makes its room
        make_room(conference, name="Elsewhere", venue=Venue.objects.create(name="E"))
        conference.event_dates.create(date=FEB)
        assert lanes(conference, FEB) == ["Convention Center"]
        assert grid_for_day(conference, FEB)["lanes"][0]["venue"] == "Convention Center"

    def test_a_room_holding_a_slot_elsewhere_keeps_its_lane(self, conference, enabled):
        conference.event_dates.create(date=MAR, venue=Venue.objects.create(name="SAP"))
        room = make_room(
            conference, name="Improving", venue=Venue.objects.create(name="I")
        )
        start = datetime(2027, 3, 14, 2, 0, tzinfo=timezone.utc)  # 13 Mar, Vancouver
        make_slot(make_session(conference), room=room, start_utc=start)
        enabled.conference_timezone = "America/Vancouver"
        enabled.save()
        assert lanes(conference, MAR) == ["SAP", "Improving"]

    def test_the_grid_shows_the_venue_under_the_room(
        self, client, organizer, enabled, conference
    ):
        hyatt = Venue.objects.create(name="Hyatt")
        conference.event_dates.create(date=FEB, venue=hyatt)
        make_room(conference, name="Ballroom A", venue=hyatt)
        client.force_login(organizer)
        content = client.get(
            reverse("speakers:schedule_editor"), {"day": "2027-02-13"}
        ).content.decode()
        assert "Ballroom A\n" in content and ">Hyatt</small>" in content
        assert 'data-room-name="Ballroom A, Hyatt"' in content


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
        response = self.start(
            client, admin_user, cadence="ONCE", conference_date="2027-05-01"
        )
        assert response.url == reverse("index")
        new = Conference.objects.get(year=2027)
        assert new.cadence == Cadence.ONCE
        assert str(new.start_date) == "2027-05-01"
        assert str(new.end_date) == "2027-05-01"

    def test_a_series_goes_to_its_dates_page(self, client, admin_user, conference):
        response = self.start(client, admin_user, cadence="SERIES")
        new = Conference.objects.get(year=2027)
        assert new.cadence == Cadence.SERIES
        assert response.url == dates_url(new)
        content = client.get(response.url).content.decode()
        assert (
            "Created Next" in content and "Now list the dates Next meets on." in content
        )

    def test_the_form_asks_which_kind_first(self, client, admin_user, conference):
        client.force_login(admin_user)
        content = client.get(reverse("start_new_year")).content.decode()
        assert "What kind of event" in content
        assert 'data-show-when="id_cadence=SERIES"' in content
        assert "id_start_date" not in content
        assert "listed next, on its Dates page" in content


@pytest.mark.django_db
def test_the_pages_say_events(client, admin_user, conference):
    assert reverse("conference_list") == "/events/"
    assert reverse("start_new_year") == "/events/start-next/"
    assert reverse("conference_edit", args=[conference.pk]).startswith("/events/")
    assert reverse("conference_tickets", args=[conference.pk]).startswith("/events/")
    assert dates_url(conference) == f"/events/{conference.pk}/dates/"


@pytest.mark.django_db
def test_span_from_nothing_changes_nothing(conference):
    before = conference.conference_date
    conference.span_from_dates()
    conference.refresh_from_db()
    assert conference.conference_date == before and conference.start_date is None


@pytest.mark.django_db
def test_venue_for_a_day(conference):
    sap = Venue.objects.create(name="SAP")
    conference.event_dates.create(date=FEB, venue=sap)
    conference.event_dates.create(date=MAR)
    assert conference.venue_for(FEB) == sap
    assert conference.venue_for(MAR) is None and conference.venue_for(MAY) is None
    conference.venue = Venue.objects.create(name="Home")
    assert conference.venue_for(MAR) == conference.venue
    assert conference.venue_for(FEB) == sap


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
        assert f"{upcoming.date.year}, Next meetup" in content
        # With the next date's own venue, else the event's.
        conference.venue = Venue.objects.create(name="Home Base")
        conference.save()
        assert "Home Base" in client.get(reverse("index")).content.decode()
        upcoming.venue = Venue.objects.create(name="Annex", url="https://a.example")
        upcoming.save()
        content = client.get(reverse("index")).content.decode()
        assert '<a href="https://a.example">Annex</a>' in content
        assert "Home Base" not in content
        upcoming.delete()
        content = client.get(reverse("index")).content.decode()
        assert "Next:" not in content
