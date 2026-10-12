from enum import StrEnum

from django.db import models

from portal.models import BaseModel, ChoiceArrayField
from ticketing.adapters import REGISTERED, Status
from ticketing.adapters.pretix import PretixAdapter
from ticketing.models import ProductKind, TicketingSettings, ticketing_for


class PretixOrderstatus(StrEnum):
    """Order status from Pretix.

    We only care about the ones canceled or paid.
    """

    CANCELLED = "c"
    PAID = "p"


EXPECTATION_FROM_EVENTS_CHOICES = [
    (
        "Learn new things",
        "Learn new things",
    ),
    ("Networking", "Networking"),
    ("Support community activities", "Support community activities"),
    ("Share Knowledge", "Share Knowledge"),
    ("Other", "Other"),
]
HEARD_ABOUT_CHOICES = [
    ("Social Media", "Social Media"),
    ("Other", "Other"),
    ("Conferences", "Conferences"),
    ("Local meetups", "Local meetups"),
]
# The "first time here" answer, matched by the Pretix question mapping below
# and counted for the first-time attendee stat.
FIRST_EVENT_ANSWER = "No this is my first one"
PARTICIPATED_IN_PREVIOUS_EVENT_CHOICES = [
    ("Yes, a previous edition", "Yes, a previous edition"),
    (FIRST_EVENT_ANSWER, FIRST_EVENT_ANSWER),
]
CURRENT_POSITION_CHOICES = [
    ("Engineer", "Engineer"),
    ("Student/Intern", "Student/Intern"),
    ("Other", "Other"),
    ("Scientist", "Scientist"),
    ("Engineering/Scientist Manager", "Engineering/Scientist Manager"),
    ("Product Owner/Manager", "Product Owner/Manager"),
    ("Hobbyist", "Hobbyist"),
    ("I'm currently retired", "I'm currently retired"),
    ("", ""),
]

PRETIX_ORDER_STATUS_CHOICES = [
    (PretixOrderstatus.CANCELLED, "Cancelled"),
    (PretixOrderstatus.PAID, "Paid"),
]

# The question identifiers that used to sit here were PyLadiesCon's own
# Pretix shop. Which question fills which field, and which answer means a
# donor stays anonymous, are per edition now: the ticketing app's settings
# row (decision 0012).


class PretixOrder(BaseModel):
    # Every order belongs to a conference edition, resolved from event_slug
    # matching Conference.pretix_event_slug (Phase 3 backfilled existing rows;
    # the webhook/fetch paths resolve it for new orders).
    # See docs/architecture/multi-year-conferences.md.
    conference = models.ForeignKey(
        "portal.Conference",
        verbose_name="event",
        on_delete=models.PROTECT,
        related_name="pretix_orders",
    )
    order_code = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=50, choices=PRETIX_ORDER_STATUS_CHOICES, null=True
    )
    email = models.EmailField(null=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    total = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=0
    )
    cancellation_date = models.DateTimeField(null=True, blank=True)
    datetime = models.DateTimeField(null=True, blank=True)
    last_modified = models.DateTimeField(null=True, blank=True)
    url = models.URLField(null=True, blank=True)
    is_anonymous = models.BooleanField(default=True, null=True, blank=True)
    event_slug = models.CharField(max_length=100, null=True)
    raw_data = models.JSONField(null=True, blank=True)
    # Decision 0012: any provider's registration, normalised. ``status``
    # keeps the provider's own code (Pretix's ``p``); ``state`` is what the
    # stats and the speakers' registration check read.
    provider = models.CharField(max_length=16, default="PRETIX")
    state = models.CharField(
        max_length=16, choices=Status.choices, blank=True, default=""
    )
    kind = models.CharField(
        max_length=16, choices=ProductKind.choices, default=ProductKind.TICKET
    )

    def __str__(self):
        return self.order_code

    @property
    def is_registered(self):
        return self.state in REGISTERED

    @staticmethod
    def resolve_conference(event_slug):
        """Map a pretix event slug to its Conference.

        Matches ``Conference.pretix_event_slug`` so a future year's orders land
        on the right edition automatically; falls back to the active conference
        when no edition declares that slug.
        """
        from portal.models import Conference

        row = (
            TicketingSettings.objects.filter(event_id=event_slug)
            .select_related("conference")
            .first()
        )
        if row is not None:
            return row.conference
        return (
            Conference.objects.filter(pretix_event_slug=event_slug).first()
            or Conference.get_active()
        )

    def from_pretix_data(self, data):
        """Populate the PretixOrder instance from pretix order data."""
        conference = self.resolve_conference(data["event"])
        row = ticketing_for(conference) or TicketingSettings(conference=conference)
        self.conference = conference
        return self.from_registration(PretixAdapter(row).normalise(data))

    def from_registration(self, registration):
        """Record a normalised registration (decision 0012). Unchanged
        since the last time (same modification stamp), nothing moves; a
        provider with no stamp (a CSV row) always updates."""
        if (
            registration.modified is not None
            and self.last_modified == registration.modified
            and self.state
        ):
            return self
        self.provider = registration.provider
        self.state = registration.status
        self.kind = registration.kind
        self.status = registration.provider_status or None
        self.email = registration.email
        self.total = registration.amount
        self.cancellation_date = registration.cancelled_at
        self.url = registration.url
        self.datetime = registration.created
        self.last_modified = registration.modified
        self.event_slug = registration.event
        if registration.name:
            self.name = registration.name
        self.set_is_anonymous_from_answers(registration.answers)
        self.raw_data = registration.raw
        return self

    def set_name_from_data(self, data):
        """Set the name field from pretix order data."""
        for pos in data["positions"]:
            if pos["attendee_name"]:
                self.name = pos["attendee_name"]
                return

    def set_is_anonymous_from_data(self, data):
        """Set the is_anonymous field from pretix order data."""
        self.set_is_anonymous_from_answers(
            {
                "question": answer["question_identifier"],
                "options": answer.get("option_identifiers") or [],
            }
            for pos in data["positions"]
            for answer in pos["answers"]
        )

    def set_is_anonymous_from_answers(self, answers):
        """The answer to the edition's anonymity question decides; with no
        such question the order stays anonymous."""
        row = ticketing_for(self.conference)
        if row is None or not row.anonymous_question:
            return
        for answer in answers:
            if answer["question"] == row.anonymous_question:
                self.is_anonymous = row.anonymous_answer in answer["options"]
                return


class AttendeeProfile(BaseModel):
    """
    Model to store anonymized attendee demographic data.
    This data is collected from pretix registration forms.
    """

    order = models.OneToOneField(
        PretixOrder, on_delete=models.CASCADE, related_name="profile"
    )

    # Demographics - all fields are nullable as responses are optional
    current_position = ChoiceArrayField(
        base_field=models.CharField(
            null=True,
            blank=True,
            help_text="Current Position",
            choices=CURRENT_POSITION_CHOICES,
        ),
        default=list,
    )
    country = models.CharField(
        max_length=100, null=True, blank=True, help_text="Current Country"
    )
    city = models.CharField(
        max_length=100, null=True, blank=True, help_text="Current City"
    )
    experience_level = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Python/programming experience level",
    )
    may_share_email_with_sponsor = models.BooleanField(
        null=True,
        blank=True,
        help_text="Permission to share email with sponsors",
    )
    expectation_from_event = ChoiceArrayField(
        base_field=models.CharField(
            null=True,
            blank=True,
            help_text="Expectations from the event",
            choices=EXPECTATION_FROM_EVENTS_CHOICES,
        ),
        default=list,
    )

    heard_about = ChoiceArrayField(
        base_field=models.CharField(
            max_length=255,
            null=True,
            blank=True,
            help_text="How did you hear about the event?",
            choices=HEARD_ABOUT_CHOICES,
        ),
        default=list,
    )
    participated_in_previous_event = ChoiceArrayField(
        base_field=models.CharField(
            null=True,
            blank=True,
            help_text="Have you participated in a previous event?",
            choices=PARTICIPATED_IN_PREVIOUS_EVENT_CHOICES,
        ),
        default=list,
    )
    pyladies_chapter = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Your local chapter or group",
    )
    age_range = models.CharField(
        max_length=100, null=True, blank=True, help_text="Age range"
    )
    organization_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Organization you work for",
    )

    # Store raw answers from pretix in case we need additional data
    raw_answers = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Attendee Profile"
        verbose_name_plural = "Attendee Profiles"

    def __str__(self):
        return f"Profile for {self.order.order_code}"

    def from_pretix_data(self, pretix_data):
        """Fill the demographic fields from the order's answers, through the
        edition's question map (decision 0012). A mapped field this order
        does not answer is cleared, so a changed answer never lingers."""
        raw = [
            answer
            for position in pretix_data.get("positions", [])
            for answer in position.get("answers", [])
        ]
        return self.from_answers(
            [
                {"question": a.get("question_identifier"), "answer": a.get("answer")}
                for a in raw
            ],
            raw=raw,
        )

    def from_answers(self, answers, raw=None):
        """Fill the fields from normalised ``{"question", "answer"}`` answers
        through the edition's question map; ``raw`` is kept as given."""
        row = ticketing_for(self.order.conference)
        mapping = (row.question_map if row else None) or {}
        answered = set()
        for answer in answers:
            field_name = mapping.get(answer.get("question"))
            if field_name is None:
                continue
            answered.add(field_name)
            self._set_answer(field_name, answer.get("answer") or "")
        all_answers = list(answers) if raw is None else raw
        for field_name in set(mapping.values()) - answered:
            field = AttendeeProfile._meta.get_field(field_name)
            setattr(
                self,
                field_name,
                [] if field.get_internal_type() == "ChoiceArrayField" else None,
            )
        self.raw_answers = all_answers
        return self

    def _set_answer(self, field_name, answer_value):
        field = AttendeeProfile._meta.get_field(field_name)
        match field.get_internal_type():
            case "BooleanField":
                setattr(self, field_name, "yes" in answer_value.lower())
            case "ChoiceArrayField":
                # The one answer with a comma of its own in the old survey.
                answer_value = answer_value.replace(
                    "No, this is my first one", FIRST_EVENT_ANSWER
                )
                setattr(
                    self,
                    field_name,
                    [part.strip() for part in answer_value.split(",")],
                )
            case _:
                setattr(
                    self,
                    field_name,
                    None if answer_value.lower() == "none" else answer_value,
                )
