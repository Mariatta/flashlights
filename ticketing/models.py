"""Where an edition's registrations come from (decision 0012).

One row per edition, replacing the ``PRETIX_*`` environment variables, the
speakers' Pretix settings and the PyLadiesCon question identifiers that
were written into the attendee app. The provider says how registrations
arrive: Pretix through its API (and webhooks), or a CSV export from
anything else. The question map says which registration question fills
which attendee field; the product map says which product is a ticket and
which a donation.
"""

from django.db import models

from portal.constants import BASE_PRETIX_URL
from speakers.encryption import EncryptedTextField, usable

#: How often the polling task runs (its schedule is seeded by migration
#: and editable under "Periodic tasks").
POLL_MINUTES = 15


class Provider(models.TextChoices):
    PRETIX = "PRETIX", "Pretix"
    CSV = "CSV", "CSV export (any provider, or a spreadsheet)"


class ProductKind(models.TextChoices):
    TICKET = "ticket", "Ticket"
    DONATION = "donation", "Donation"


#: The attendee fields a registration question can fill, with the label an
#: organiser picks from. Field names are the attendee profile's (upstream).
ATTENDEE_FIELDS = [
    ("city", "City"),
    ("country", "Country"),
    ("organization_name", "Organisation"),
    ("current_position", "Current position"),
    ("experience_level", "Experience level"),
    ("age_range", "Age range"),
    ("pyladies_chapter", "Local chapter or group"),
    ("heard_about", "How they heard about the event"),
    ("expectation_from_event", "What they expect from the event"),
    ("participated_in_previous_event", "Came to a previous edition"),
    ("may_share_email_with_sponsor", "May share email with sponsors"),
]
ATTENDEE_FIELD_NAMES = {name for name, _ in ATTENDEE_FIELDS}


class TicketingSettings(models.Model):
    conference = models.OneToOneField(
        "portal.Conference",
        verbose_name="event",
        on_delete=models.CASCADE,
        related_name="ticketing",
    )
    provider = models.CharField(
        max_length=16, choices=Provider.choices, default=Provider.PRETIX
    )
    base_url = models.URLField(
        "API base URL",
        default=BASE_PRETIX_URL,
        help_text="Pretix: the API root, ending in /api/v1/.",
    )
    organizer = models.CharField(
        max_length=100, blank=True, help_text="Pretix: the organizer slug."
    )
    event_id = models.CharField(
        "event", max_length=100, blank=True, help_text="Pretix: the event slug."
    )
    api_token = EncryptedTextField("API token", blank=True, default="")
    webhook_secret = EncryptedTextField(
        blank=True,
        default="",
        help_text="Pretix sends it as ?secret= on the webhook URL.",
    )
    question_map = models.JSONField(
        default=dict,
        blank=True,
        help_text="Registration question id to attendee field.",
    )
    product_map = models.JSONField(
        default=dict,
        blank=True,
        help_text="Product id to ticket or donation.",
    )
    anonymous_question = models.CharField(
        max_length=100,
        blank=True,
        help_text="The question donors answer to stay anonymous.",
    )
    anonymous_answer = models.CharField(
        max_length=100,
        blank=True,
        help_text="The answer to that question that means anonymous.",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    modified_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ticketing settings"
        verbose_name_plural = "ticketing settings"

    def __str__(self):
        return f"Ticketing for {self.conference}"

    @property
    def has_api(self):
        """Registrations can be fetched: Pretix with an organizer, an event
        and a token this deploy can decrypt (an undecryptable token reads as
        not configured, so a missing key degrades ticketing alone)."""
        return bool(
            self.provider == Provider.PRETIX
            and self.organizer
            and self.event_id
            and usable(self.api_token)
        )

    @property
    def is_set_up(self):
        """Registrations exist somewhere: an API, or CSV imports."""
        return self.has_api or self.provider == Provider.CSV


def carry_forward(target, source, event_id=""):
    """Next year's ticketing: the same shop, account and maps as ``source``,
    a new event. Nothing to carry when ``source`` has no row; ``event_id``
    alone still makes one, since that is what the start-of-year form asks."""
    row = ticketing_for(source)
    if row is None:
        if event_id:
            return TicketingSettings.objects.create(
                conference=target, event_id=event_id
            )
        return None
    fields = {
        name: getattr(row, name)
        for name in (
            "provider",
            "base_url",
            "organizer",
            "question_map",
            "product_map",
            "anonymous_question",
            "anonymous_answer",
        )
    }
    # Secrets only when this deploy can read them: an undecryptable value
    # cannot be written again.
    for name in ("api_token", "webhook_secret"):
        value = getattr(row, name)
        fields[name] = value if usable(value) else ""
    return TicketingSettings.objects.create(
        conference=target, event_id=event_id, **fields
    )


def ticketing_for(conference):
    """The edition's ticketing row, or None."""
    if conference is None:
        return None
    return TicketingSettings.objects.filter(conference=conference).first()


def has_api(conference):
    row = ticketing_for(conference)
    return bool(row and row.has_api)


def is_set_up(conference):
    row = ticketing_for(conference)
    return bool(row and row.is_set_up)
