"""Rooms follow venues: an edition gets a room the moment it picks one."""

from .constants import RoomKind
from .models import Room, event_tz


def room_for_venue(conference, venue):
    """The edition's first room at ``venue``, made when there is none, so
    the place is schedulable as soon as it is picked: a meetup's one room,
    or a conference's first lane to rename and extend. A room named after
    the venue that has no venue yet becomes its room rather than getting
    a twin. Returns the room made or adopted, None when one was there."""
    if Room.objects.filter(conference=conference, venue=venue).exists():
        return None
    room, created = Room.objects.get_or_create(
        conference=conference,
        name=venue.name,
        venue=None,
        defaults={"kind": RoomKind.ROOM, "venue": venue},
    )
    if not created:
        room.venue = venue
        room.save()
    return room


class Locations:
    """Where slots of one edition are, for a calendar or an email: the
    room with its venue ("Ballroom A, Hyatt"), or "All rooms" with the
    venue of the slot's day (the event's own day, where a series lists its
    dates). A room without a venue is at the day's, which is nothing
    online. The timezone and the venues are read once, however many slots
    are asked about."""

    def __init__(self, conference):
        self.conference = conference
        self.tz = event_tz(conference)

    def __call__(self, start_utc, room=None):
        if room and room.venue_id:
            return room.label  # its own venue, whatever the day
        where = room.name if room else "All rooms"
        venue = self.conference.venue_for(start_utc.astimezone(self.tz).date())
        return f"{where}, {venue.name}" if venue else where
