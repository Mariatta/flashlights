"""Rooms follow venues: an edition gets a room the moment it picks one."""

from .constants import RoomKind
from .models import Room


def room_for_venue(conference, venue):
    """The edition's first room at ``venue``, made when there is none, so
    the place is schedulable as soon as it is picked: a meetup's one room,
    or a conference's first lane to rename and extend. A room already
    named after the venue becomes its room rather than getting a twin.
    Returns the room made or adopted, None when one was there."""
    if Room.objects.filter(conference=conference, venue=venue).exists():
        return None
    room, created = Room.objects.get_or_create(
        conference=conference,
        name=venue.name,
        defaults={"kind": RoomKind.ROOM, "venue": venue},
    )
    if not created:
        room.venue = venue
        room.save()
    return room
