"""Ticketing providers behind one interface.

An adapter turns a provider's orders into ``Registration`` records: the
fields every provider has (a code, a status, who, how much, when, the
answers), with the provider's own record kept as ``raw``. Statuses are
normalised to paid, free, pending, cancelled and refunded; whether an
order is a ticket or a donation comes from the edition's product map.

Pretix is the first adapter; CSV import (any provider, or a spreadsheet)
and Eventbrite, Luma or Tito follow the same shape.
"""

from .base import REGISTERED, Adapter, Registration, Status
from .csv import CsvAdapter
from .pretix import PretixAdapter

__all__ = [
    "REGISTERED",
    "Adapter",
    "CsvAdapter",
    "Registration",
    "Status",
    "adapter_for",
]

ADAPTERS = {PretixAdapter.provider: PretixAdapter, CsvAdapter.provider: CsvAdapter}


def adapter_for(ticketing, **kwargs):
    """The adapter for an edition's ticketing row, or None when the
    provider has no API to read from."""
    if ticketing is None or not ticketing.has_api:
        return None
    return ADAPTERS[ticketing.provider](ticketing, **kwargs)
