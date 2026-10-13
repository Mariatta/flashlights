"""The Pretix adapter (design §12.1): the REST client with
pagination and retry, ported from the speakers' and the attendee app's two
clients, and the normalisation of a Pretix order."""

import time
from decimal import Decimal

import requests

from ticketing.models import Provider

from .base import Adapter, Registration, Status

WEBHOOK_ACTIONS = {
    "pretix.event.order.placed",
    "pretix.event.order.paid",
    "pretix.event.order.canceled",
    "pretix.event.order.expired",
    "pretix.event.order.changed",
}
RETRY_STATUSES = {429, 500, 502, 503, 504}

#: Pretix's order status codes. A paid order of nothing is a free one.
PRETIX_STATUSES = {
    "p": Status.PAID,
    "n": Status.PENDING,
    "e": Status.CANCELLED,
    "c": Status.CANCELLED,
}


class PretixError(Exception):
    """The pretix API refused or failed after retries."""


class PretixClient:
    """Thin client over the pretix REST API with pagination and retry."""

    def __init__(self, ticketing, attempts=3, backoff=1.0):
        """``ticketing`` is the edition's ``TicketingSettings`` row."""
        self.base_url = ticketing.base_url.rstrip("/") + "/"
        self.organizer = ticketing.organizer
        self.event = ticketing.event_id
        self.headers = {"Authorization": f"Token {ticketing.api_token}"}
        self.attempts = attempts
        self.backoff = backoff

    @property
    def orders_url(self):
        return f"{self.base_url}organizers/{self.organizer}/events/{self.event}/orders/"

    def _get(self, url, params=None):
        last_error = None
        for attempt in range(self.attempts):
            try:
                response = requests.get(
                    url, headers=self.headers, params=params, timeout=30
                )
            except requests.RequestException as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
            else:
                if response.status_code == 200:
                    return response.json()
                last_error = f"{response.status_code} {response.text[:200]}"
                if response.status_code not in RETRY_STATUSES:
                    break
            if attempt + 1 < self.attempts:
                time.sleep(self.backoff * (attempt + 1))
        raise PretixError(f"GET {url} failed: {last_error}")

    def get_order(self, code):
        return self._get(f"{self.orders_url}{code}/")

    def iter_orders(self, modified_since=None, email=None):
        """Yield orders page by page. ``modified_since`` is a datetime."""
        params = {}
        if modified_since is not None:
            params["modified_since"] = modified_since.isoformat()
        if email:
            params["email"] = email
        url = self.orders_url
        while url:
            page = self._get(url, params=params)
            params = None  # the ``next`` link already carries the query
            yield from page.get("results", [])
            url = page.get("next")


class PretixAdapter(Adapter):
    provider = Provider.PRETIX
    supports_webhooks = True

    def __init__(self, ticketing, client=None):
        """``client`` stands in for the REST client (tests, or a caller
        that already has one); by default one is made from the row."""
        super().__init__(ticketing)
        self.client = client or PretixClient(ticketing)

    def get(self, code):
        return self.normalise(self.client.get_order(code))

    def iter_registrations(self, since=None, email=None):
        if email:
            orders = self.client.iter_orders(email=email)
        else:
            orders = self.client.iter_orders(modified_since=since)
        for raw in orders:
            yield self.normalise(raw)

    def normalise(self, raw):
        positions = raw.get("positions") or []
        amount = Decimal(str(raw.get("total") or 0))
        status = PRETIX_STATUSES.get(raw.get("status"), Status.PENDING)
        if status == Status.PAID and not amount:
            status = Status.FREE
        name = next(
            (pos["attendee_name"] for pos in positions if pos.get("attendee_name")), ""
        )
        return Registration(
            provider=self.provider,
            code=raw["code"],
            status=status,
            kind=self.kind_of(pos.get("item") for pos in positions),
            email=raw.get("email") or "",
            name=name,
            amount=amount,
            event=raw.get("event") or "",
            url=raw.get("url") or "",
            created=raw.get("datetime"),
            modified=raw.get("last_modified"),
            cancelled_at=raw.get("cancellation_date"),
            provider_status=raw.get("status") or "",
            attendee_emails=[
                pos["attendee_email"] for pos in positions if pos.get("attendee_email")
            ],
            answers=[
                {
                    "question": answer.get("question_identifier"),
                    "answer": answer.get("answer"),
                    "options": answer.get("option_identifiers") or [],
                }
                for pos in positions
                for answer in pos.get("answers") or []
            ],
            raw=raw,
        )
