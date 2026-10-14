"""Venues: places kept once and picked by editions and rooms."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from portal.models import Conference, Venue
from speakers.models import Room
from speakers.seeds import clone_speaker_setup
from tests.grants import on_team
from tests.speakers.factories import make_settings


@pytest.fixture
def organizer(db):
    return on_team(User.objects.create_user(username="org", email="org@x.org"))


def venue_data(**extra):
    return {
        "name": "SAP",
        "address": "910 Mainland St",
        "url": "",
        "notes": "",
        **extra,
    }


@pytest.mark.django_db
class TestVenuePages:
    def test_add_edit_and_list(self, client, organizer, conference):
        client.force_login(organizer)
        assert client.post(reverse("venue_create"), venue_data()).status_code == 302
        venue = Venue.objects.get(name="SAP")
        client.post(
            reverse("venue_edit", args=[venue.pk]),
            venue_data(url="https://maps.example.org/sap"),
        )
        venue.refresh_from_db()
        assert venue.url == "https://maps.example.org/sap"
        content = client.get(reverse("venue_list")).content.decode()
        assert "910 Mainland St" in content and "0 events" in content
        # The rail offers Venues next to Events.
        assert (
            reverse("venue_list") in content and reverse("conference_list") in content
        )

    def test_delete_refused_while_in_use(self, client, organizer, conference):
        client.force_login(organizer)
        venue = Venue.objects.create(name="SAP")
        conference.venue = venue
        conference.save()
        response = client.post(reverse("venue_delete", args=[venue.pk]), follow=True)
        assert "Cannot delete SAP" in response.content.decode()
        assert Venue.objects.filter(pk=venue.pk).exists()
        conference.venue = None
        conference.save()
        conference.rooms.all().delete()
        client.post(reverse("venue_delete", args=[venue.pk]))
        assert not Venue.objects.filter(pk=venue.pk).exists()

    def test_only_event_editors(self, client, portal_user, conference):
        client.force_login(portal_user)
        for url in (reverse("venue_list"), reverse("venue_create")):
            assert client.get(url).status_code in (302, 403)


@pytest.mark.django_db
class TestRoomForVenue:
    def test_picking_a_venue_makes_its_room_once(self, conference):
        venue = Venue.objects.create(name="SAP")
        conference.venue = venue
        conference.save()
        room = Room.objects.get(conference=conference)
        assert (room.name, room.venue) == ("SAP", venue)
        # Saved again, renamed or not: no twin.
        room.name = "SAP, room 5"
        room.save()
        conference.save()
        assert Room.objects.filter(conference=conference).count() == 1
        # A save that does not touch the venue does not even look.
        conference.rooms.all().delete()
        conference.save(update_fields=["name"])
        assert not Room.objects.filter(conference=conference).exists()

    def test_a_room_named_after_the_venue_is_adopted(self, conference):
        existing = Room.objects.create(conference=conference, name="SAP")
        conference.venue = Venue.objects.create(name="SAP")
        conference.save()
        existing.refresh_from_db()
        assert existing.venue == conference.venue
        assert Room.objects.filter(conference=conference).count() == 1

    def test_rooms_are_carried_to_the_next_edition(self, conference):
        venue = Venue.objects.create(name="Convention Center")
        Room.objects.create(conference=conference, name="201A", venue=venue, url="u")
        Room.objects.create(conference=conference, name="Old", is_active=False)
        target = Conference.objects.create(year=2099, name="Next", slug="next")
        counts = clone_speaker_setup(target, conference)
        assert counts["rooms"] == 1
        room = Room.objects.get(conference=target)
        assert (room.name, room.venue, room.url) == ("201A", venue, "u")
        # Again: nothing doubled.
        assert clone_speaker_setup(target, conference)["rooms"] == 0


@pytest.mark.django_db
class TestRoomVenue:
    def test_a_room_picks_its_venue(self, client, organizer, conference):
        make_settings(conference, event_format="IN_PERSON")
        client.force_login(organizer)
        venue = Venue.objects.create(name="Convention Center")
        conference.venue = venue
        conference.save()
        Room.objects.filter(conference=conference).delete()
        page = client.get(reverse("speakers:room_create"))
        assert page.context["form"].fields["venue"].initial == venue.pk
        assert reverse("venue_create") in page.content.decode()
        other = Venue.objects.create(name="Annex")
        client.post(
            reverse("speakers:room_create"),
            {"name": "201A", "kind": "ROOM", "venue": other.pk, "is_active": "on"},
        )
        assert Room.objects.get(name="201A").venue == other
        # Editing keeps the room's own venue, not the edition's.
        room = Room.objects.get(name="201A")
        assert (
            client.get(reverse("speakers:room_edit", args=[room.pk]))
            .context["form"]
            .initial["venue"]
            == other.pk
        )
        Room.objects.create(conference=conference, name="Stream")
        listing = client.get(reverse("speakers:room_list")).content.decode()
        assert "Annex" in listing and "Online" in listing

    def test_an_online_edition_has_no_venue_column(self, client, organizer, conference):
        make_settings(conference)
        client.force_login(organizer)
        assert (
            client.get(reverse("speakers:room_create"))
            .context["form"]
            .fields["venue"]
            .initial
            is None
        )
        Room.objects.create(conference=conference, name="Stream")
        listing = client.get(reverse("speakers:room_list")).content.decode()
        assert ">Venue<" not in listing
