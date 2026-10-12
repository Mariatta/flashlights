"""Pretix integration (design §12.1): API client, order upsert, webhook and
nightly reconciliation helpers.

Orders land in ``attendee.PretixOrder`` (the portal's existing per-edition
order record), so the speaker rules, the attendee stats and the manual link
all read the same rows.
"""

import logging

from django.utils import timezone

from attendee.models import AttendeeProfile, PretixOrder
from ticketing.adapters.pretix import (  # noqa: F401 - re-exported for callers
    WEBHOOK_ACTIONS,
    PretixAdapter,
    PretixClient,
    PretixError,
)
from ticketing.models import TicketingSettings, ticketing_for

from .models import ActivityLog, SpeakerSettings

logger = logging.getLogger(__name__)


def _adapter(conference, client):
    """The edition's Pretix adapter over ``client``, a REST client (the
    real one from ``client_for``, or a stand-in in tests)."""
    row = ticketing_for(conference) or TicketingSettings(conference=conference)
    return PretixAdapter(row, client=client)


def upsert_order(conference, data):
    """Record one pretix order, given as pretix's own record."""
    return upsert_registration(conference, _adapter(conference, None).normalise(data))


def upsert_registration(conference, registration):
    """Record one normalised registration (decision 0012), and the attendee
    profile for anyone registered (paid or free).

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


def client_for(conference):
    """A client for the edition, or None when it has no Pretix API set up."""
    row = ticketing_for(conference)
    if row is None or not row.has_api:
        return None
    return PretixClient(row)


def sync_order_by_code(conference, code, client=None):
    """Re-fetch one order from pretix and upsert it (the webhook path)."""
    client = client or client_for(conference)
    order, _ = upsert_registration(conference, _adapter(conference, client).get(code))
    return order


def reconcile(conference, client=None):
    """Page through orders modified since the last run and upsert them all.

    Returns the number of orders seen. Advances the ticketing row's
    ``last_synced_at`` to the start of the run so a webhook missed meanwhile
    is caught next time.
    """
    row = TicketingSettings.objects.get(conference=conference)
    client = client or PretixClient(row)
    started = timezone.now()
    seen = 0
    for registration in _adapter(conference, client).iter_registrations(
        since=row.last_synced_at
    ):
        upsert_registration(conference, registration)
        seen += 1
    row.last_synced_at = started
    row.save(update_fields=["last_synced_at", "modified_date"])
    ActivityLog.record(
        conference, "pretix.reconciled", message=f"{seen} order(s) refreshed"
    )
    return seen


def lookup_presenter_orders(presenter, actor=None, client=None):
    """Ask pretix for orders under the presenter's email and record them.

    Returns the orders found; the ``pretix_registered`` rule then ticks the
    item through the PretixOrder save signal.
    """
    client = client or client_for(presenter.conference)
    if client is None:
        return None
    adapter = _adapter(presenter.conference, client)
    orders = [
        upsert_registration(presenter.conference, registration)[0]
        for registration in adapter.iter_registrations(email=presenter.email)
    ]
    ActivityLog.record(
        presenter.conference,
        "pretix.lookup",
        target=presenter,
        actor=actor,
        message=f"{len(orders)} order(s) found for {presenter.email}",
    )
    return orders


def link_presenter_order(presenter, code, actor=None, client=None):
    """Point a presenter at an order by code, fetching it if unknown locally.

    A manual link wins over email matching (design §12.1).
    """
    order = PretixOrder.objects.filter(
        order_code=code, conference=presenter.conference
    ).first()
    if order is None:
        client = client or client_for(presenter.conference)
        if client is None:
            raise PretixError("Pretix is not configured for this edition.")
        order = sync_order_by_code(presenter.conference, code, client=client)
    presenter.pretix_order = order
    presenter.save(update_fields=["pretix_order", "modified_date"])
    ActivityLog.record(
        presenter.conference,
        "pretix.linked",
        target=presenter,
        actor=actor,
        message=f"Linked to order {order.order_code}",
    )
    return order


def unlink_presenter_order(presenter, actor=None):
    presenter.pretix_order = None
    presenter.save(update_fields=["pretix_order", "modified_date"])
    ActivityLog.record(
        presenter.conference, "pretix.unlinked", target=presenter, actor=actor
    )


def create_voucher(presenter):
    """Voucher creation is optional and not built yet (design §12.1).

    Behind ``SpeakerSettings.pretix_create_vouchers``: off returns None;
    on raises so nobody believes a voucher was issued.
    """
    settings_row = SpeakerSettings.objects.filter(
        conference=presenter.conference
    ).first()
    if settings_row is None or not settings_row.pretix_create_vouchers:
        return None
    raise NotImplementedError("Pretix voucher creation is not implemented yet.")
