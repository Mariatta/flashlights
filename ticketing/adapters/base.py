"""The adapter interface and the normalised registration (decision 0012)."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.db import models

from ticketing.models import ProductKind


class Status(models.TextChoices):
    PAID = "paid", "Paid"
    FREE = "free", "Free"
    PENDING = "pending", "Pending"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


#: The states that mean someone is coming.
REGISTERED = (Status.PAID, Status.FREE)


@dataclass
class Registration:
    """One order, normalised. ``answers`` are ``{"question", "answer",
    "options"}`` dicts in the provider's own question ids."""

    provider: str
    code: str
    status: str
    kind: str = ProductKind.TICKET
    email: str = ""
    name: str = ""
    amount: Decimal = Decimal("0")
    currency: str = ""
    event: str = ""
    url: str = ""
    created: datetime | str | None = None
    modified: datetime | str | None = None
    cancelled_at: datetime | str | None = None
    provider_status: str = ""
    attendee_emails: list = field(default_factory=list)
    answers: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def is_registered(self):
        return self.status in REGISTERED


class Adapter:
    """The interface every provider implements. ``ticketing`` is the
    edition's ``TicketingSettings`` row."""

    provider = None
    #: Whether the provider can call us when an order changes. Polling is
    #: the baseline either way; a webhook only makes it instant.
    supports_webhooks = False

    def __init__(self, ticketing):
        self.ticketing = ticketing

    def get(self, code):
        """One registration by its code."""
        raise NotImplementedError

    def iter_registrations(self, since=None, email=None):
        """Registrations changed since ``since``, or under ``email``."""
        raise NotImplementedError

    def normalise(self, raw):
        """The provider's record as a ``Registration``."""
        raise NotImplementedError

    def kind_of(self, products):
        """Ticket or donation, from the edition's product map: a donation
        only when every product on the order is mapped as one."""
        mapping = self.ticketing.product_map or {}
        kinds = {mapping.get(str(product), ProductKind.TICKET) for product in products}
        if kinds == {ProductKind.DONATION}:
            return ProductKind.DONATION
        return ProductKind.TICKET
