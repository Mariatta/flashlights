"""Recording registrations, whatever the provider."""

import csv
import io
from dataclasses import dataclass, field

from django.utils import timezone

from attendee.models import AttendeeProfile, PretixOrder

from .adapters import CsvAdapter, adapter_for
from .adapters.csv import headers as column_headers


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


class CsvImportError(ValueError):
    """The file cannot be read as this edition's export."""


@dataclass
class ImportResult:
    imported: int = 0
    registered: int = 0
    skipped: list = field(default_factory=list)  # (line, reason)


def import_csv(ticketing, content):
    """Record every row of a CSV export (bytes or text) for the edition.

    Rows are upserted by code (or email): importing a newer export updates
    people and adds new ones; someone missing from it is left as they were,
    since an export filtered by date would otherwise cancel everyone else.
    """
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CsvImportError("Save the file as UTF-8 CSV and try again.") from exc
    columns = ticketing.csv_columns or {}
    if not columns.get("email"):
        raise CsvImportError("Map the email column on the Tickets page first.")
    reader = csv.DictReader(io.StringIO(content))
    present = reader.fieldnames or []
    missing = sorted(
        header
        for spec in columns.values()
        for header in column_headers(spec)
        if header not in present
    )
    if missing:
        raise CsvImportError(
            "The file has no column named " + ", ".join(repr(h) for h in missing) + "."
        )
    adapter = CsvAdapter(ticketing)
    result = ImportResult()
    for line, row in enumerate(reader, start=2):
        registration = adapter.normalise(row)
        if "@" not in registration.email:
            result.skipped.append((line, "no email address"))
            continue
        upsert_registration(ticketing.conference, registration)
        result.imported += 1
        result.registered += registration.is_registered
    return result
