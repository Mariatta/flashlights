"""The CSV adapter: a spreadsheet export from any ticketing
system, or a plain list of the people registered.

The edition's column map says which header holds the email, the name, the
code, the status, the amount, the date and the ticket type; every other
column is kept as an answer, under its header, for the question map.
"""

import hashlib
import re
from datetime import UTC, datetime, time
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from ticketing.models import ProductKind, Provider

from .base import Adapter, Registration, Status

#: Status words seen in exports, lower-cased. A file with no status column
#: is a list of people registered.
STATUS_WORDS = {
    Status.PAID: {
        "paid",
        "complete",
        "completed",
        "confirmed",
        "registered",
        "attending",
        "active",
        "valid",
        "yes",
    },
    Status.FREE: {"free"},
    Status.PENDING: {
        "pending",
        "unpaid",
        "waitlist",
        "waitlisted",
        "reserved",
        "awaiting payment",
    },
    Status.CANCELLED: {
        "cancelled",
        "canceled",
        "void",
        "voided",
        "declined",
        "expired",
        "no",
    },
    Status.REFUNDED: {"refunded", "refund"},
}
WORD_STATUS = {word: status for status, words in STATUS_WORDS.items() for word in words}


def headers(spec):
    """The column headers a mapping names: one, or several joined by " + "."""
    return [part.strip() for part in (spec or "").split(" + ") if part.strip()]


def parse_amount(value):
    """``"$1,250.00"``, ``"25"``, ``""``: the number, or zero."""
    cleaned = re.sub(r"[^0-9.\-]", "", value or "")
    try:
        return Decimal(cleaned) if cleaned else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def parse_when(value):
    """An ISO date or date-time, made aware in UTC when it has no zone."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        moment = parse_datetime(value)
        if moment is None:
            day = parse_date(value)
            moment = datetime.combine(day, time()) if day else None
    except ValueError:
        return None
    if moment is not None and timezone.is_naive(moment):
        moment = timezone.make_aware(moment, UTC)
    return moment


class CsvAdapter(Adapter):
    provider = Provider.CSV

    def status_of(self, word, amount):
        """Unknown words count as pending: a row is only counted as coming
        when the file says so, or says nothing."""
        word = (word or "").strip().lower()
        status = WORD_STATUS.get(word, Status.PENDING) if word else Status.PAID
        if status == Status.PAID and not amount:
            return Status.FREE
        return status

    def code_for(self, value):
        """Codes are unique across every edition and provider: prefixed
        with the edition, and hashed when that would not fit."""
        code = f"csv-{self.ticketing.conference.slug}-{value}"
        if len(code) > 100:
            code = "csv-" + hashlib.sha256(code.encode()).hexdigest()
        return code

    def normalise(self, row):
        columns = self.ticketing.csv_columns or {}

        def value(field):
            # "First Name + Last Name": several columns, joined by a space,
            # for exports that split what we keep as one field.
            parts = [(row.get(h) or "").strip() for h in headers(columns.get(field))]
            return " ".join(part for part in parts if part)

        email = value("email").lower()
        amount = parse_amount(value("amount"))
        status_word = value("status")
        product = value("product")
        mapped = {h for spec in columns.values() for h in headers(spec)}
        kind = self.kind_of([product]) if product else ProductKind.TICKET
        return Registration(
            provider=self.provider,
            code=self.code_for(value("code") or email),
            status=self.status_of(status_word, amount),
            kind=kind,
            # One amount per row: a donation only when the row's product is.
            donation=amount if kind == ProductKind.DONATION else Decimal("0"),
            email=email,
            name=value("name"),
            amount=amount,
            created=parse_when(value("created")),
            provider_status=status_word[:50],
            attendee_emails=[email] if email else [],
            answers=[
                {"question": header, "answer": (answer or "").strip(), "options": []}
                for header, answer in row.items()
                if header and header not in mapped
            ],
            raw=dict(row),
        )
