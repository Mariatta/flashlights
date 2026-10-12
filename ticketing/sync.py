"""Recording registrations, whatever the provider (decision 0012)."""

from django.utils import timezone

from attendee.models import AttendeeProfile, PretixOrder

from .adapters import adapter_for


def upsert_registration(conference, registration):
    """Record one normalised registration, and the attendee profile for
    anyone registered (paid or free).

    The edition is the one given: the order's event slug may name another
    edition, or none, and the caller knows which shop it asked.
    """
    order, created = PretixOrder.objects.get_or_create(
        order_code=registration.code, defaults={"conference": conference}
    )
    order.conference = conference
    order.from_registration(registration)
    order.save()
    if order.is_registered:
        profile, _ = AttendeeProfile.objects.get_or_create(order=order)
        profile.from_answers(registration.answers)
        profile.save()
    return order, created


def sync(ticketing, adapter=None):
    """Record every registration changed since the last run. Returns how
    many were seen; advances ``last_synced_at`` to the start of the run,
    so one changed meanwhile is caught next time. ``adapter`` stands in
    for the edition's own (a test, or a caller with a client in hand)."""
    adapter = adapter or adapter_for(ticketing)
    started = timezone.now()
    seen = 0
    for registration in adapter.iter_registrations(since=ticketing.last_synced_at):
        upsert_registration(ticketing.conference, registration)
        seen += 1
    ticketing.last_synced_at = started
    ticketing.save(update_fields=["last_synced_at", "modified_date"])
    return seen
