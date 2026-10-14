from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import dateformat
from django.utils.timezone import now


class ChoiceArrayField(ArrayField):

    def formfield(self, **kwargs):  # pragma: no cover
        # Currently this is only used the languages_spoken field but the field is being deprecated
        defaults = {
            "form_class": forms.TypedMultipleChoiceField,
            "choices": self.base_field.choices,
            "coerce": self.base_field.to_python,
            "widget": FilteredSelectMultiple(self.verbose_name, False),
        }
        defaults.update(kwargs)
        return super(ArrayField, self).formfield(**defaults)


class BaseModel(models.Model):
    creation_date = models.DateTimeField(
        "creation_date", editable=False, auto_now_add=True
    )
    modified_date = models.DateTimeField("modified_date", editable=False, auto_now=True)

    def save(self, *args, **kwargs):
        self.modified_date = now()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "modified_date" not in update_fields:
            # A list from callers, a set from update_or_create: add to either
            # without mutating what the caller passed.
            kwargs["update_fields"] = [*update_fields, "modified_date"]
        super().save(*args, **kwargs)


class ChatPlatform(models.TextChoices):
    """Where an edition's team, speakers and attendees talk.
    Discord is what the portal was built around (channel ids, roles);
    another platform gets a name and an invite link; none gets nothing."""

    NONE = "NONE", "No community chat"
    DISCORD = "DISCORD", "Discord"
    OTHER = "OTHER", "Another platform"


class Cadence(models.TextChoices):
    """How an edition meets: once a year, on one day or a run of days
    (a conference, a summit), or as a series of separate dates (a
    meetup chapter's year). Decides which dates the edition forms ask for
    and which days the schedule editor offers."""

    ONCE = "ONCE", "One event a year: a conference or a summit"
    SERIES = "SERIES", "A series of separate dates: a year of meetups"


class Venue(models.Model):
    """A place an edition happens at: a building, or one room with an
    address. Kept once per instance and picked by editions, dates and
    rooms, so a community returning to the same building names it once.
    """

    name = models.CharField(max_length=200, unique=True)
    address = models.TextField(blank=True)
    url = models.URLField(
        "link", blank=True, help_text="A map or the venue's own page."
    )
    notes = models.TextField(
        blank=True,
        help_text="For the team, not published: how to get in, parking, "
        "accessibility, who to call.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Conference(BaseModel):
    """A single edition of the event (2023, 2024, 2025, ...).

    Anchors all per-year configuration. Exactly one conference is active at a
    time; see ``save()`` and ``get_active()``. See
    ``docs/architecture/multi-year-conferences.md`` for the full design.
    """

    # BaseModel is concrete (multi-table inheritance), so without this
    # explicit parent link Django adds a reverse accessor named "conference"
    # to BaseModel — clashing with the per-year ``conference`` FK that other
    # models gain. related_name="+" suppresses that accessor.
    basemodel_ptr = models.OneToOneField(
        BaseModel,
        on_delete=models.CASCADE,
        parent_link=True,
        primary_key=True,
        related_name="+",
    )

    year = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=False)
    pretix_event_slug = models.CharField(max_length=100, blank=True)

    # year-bound config (replaces hardcoded constants)
    sponsorship_goal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    donation_goal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    proposals_count = models.PositiveIntegerField(default=0)

    # year-bound state flags
    volunteer_application_open = models.BooleanField(default=False)
    sponsorship_open = models.BooleanField(default=False)
    accepting_donations = models.BooleanField(default=True)

    # Once a year or a series: the forms ask for the event date and its
    # last day, or for the listed dates, and refuse an edition without
    # either, so the schedule never offers a whole year of days.
    cadence = models.CharField(
        max_length=8,
        choices=Cadence.choices,
        default=Cadence.ONCE,
        db_default=Cadence.ONCE,
        help_text="Once a year: the event date and, for a run of days, the "
        "last day. A series: the dates it meets on, listed one by one.",
    )
    # optional metadata
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    # When this edition takes place. Next year's conference can only be started
    # once this date has passed. Null for a freshly-created edition.
    conference_date = models.DateField(null=True, blank=True)
    banner_text = models.CharField(max_length=255, blank=True)
    # Where it happens: a venue from the instance's list, printed on the
    # landing page, the public program and the calendar feeds. Blank for
    # an online edition. An edition that picks one gets a room at it when
    # it has none (speakers.rooms).
    venue = models.ForeignKey(
        Venue,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="editions",
        help_text="Leave blank online. Venues are added on the Venues page.",
    )
    # Community chat. Editions from before read Discord,
    # which is what the portal assumed.
    chat_platform = models.CharField(
        max_length=16,
        choices=ChatPlatform.choices,
        default=ChatPlatform.DISCORD,
        db_default=ChatPlatform.DISCORD,
        help_text="Discord: speakers and volunteers are asked for their "
        "username, rooms may be channels. Another platform: a name and an "
        "invite link, nothing else. None: no chat is mentioned.",
    )
    chat_name = models.CharField(
        "chat platform name",
        max_length=60,
        blank=True,
        help_text="For another platform: Slack, Zulip, Matrix...",
    )
    chat_url = models.URLField("chat invite link", blank=True)
    # Where replies to the portal's email go: the team's own inbox or list
    # (a Google Group works), since mail is sent from a no-reply address.
    reply_to_email = models.EmailField(
        "reply-to address",
        blank=True,
        help_text="Replies to every email this edition sends go here, for "
        "example the team's Google Group. Leave blank and replies go to the "
        "sending address.",
    )

    # Per-edition external links. Organizers set these per year; when blank the
    # templates fall back to a sensible default.
    sponsors_url = models.URLField(blank=True, null=True)
    coc_url = models.URLField(blank=True, null=True)
    donate_url = models.URLField(blank=True, null=True)
    schedule_url = models.URLField(blank=True, null=True)

    # snapshot of closed-out year metrics (used when no portal data exists,
    # e.g. for 2023 and 2024, and for "freezing" past years)
    historical_snapshot = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ["-year"]
        # The class keeps its upstream name; people read "event".
        verbose_name = "event"
        verbose_name_plural = "events"
        # The organizer surface and the year rollover are capabilities,
        # not flags. Read through has_perm, granted by teams.
        permissions = [
            ("view_organizer_dashboard", "Can open the organizer dashboard"),
            ("start_next_year", "Can start the next edition"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_active:
            Conference.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Return the active conference, or ``None`` if none is set."""
        return cls.objects.filter(is_active=True).first()

    @property
    def reply_to(self):
        """The reply-to list for this edition's email, or None when unset."""
        return [self.reply_to_email] if self.reply_to_email else None

    @property
    def uses_discord(self):
        return self.chat_platform == ChatPlatform.DISCORD

    @property
    def has_chat(self):
        return self.chat_platform != ChatPlatform.NONE

    @property
    def chat_label(self):
        """What to call the chat in a sentence: "Discord", the platform's
        name, or "the event chat" when another platform has no name."""
        if self.uses_discord:
            return "Discord"
        return self.chat_name or "the event chat"

    @classmethod
    def can_start_next_year(cls):
        """Whether the "start a new year" flow should be available.

        Available while no edition newer than the active one exists, so the
        next edition can be set up and planned while the current one is
        still running; activating it is the rollover. When there is no
        active edition at all, it is available so the first edition can be
        created.
        """
        active = cls.get_active()
        if active is None:
            return True
        return not cls.objects.filter(year__gt=active.year).exists()

    @property
    def next_event_date(self):
        """The first listed event date from today on, or None when the
        edition lists none still to come."""
        return self.event_dates.filter(date__gte=now().date()).first()

    def span_from_dates(self):
        """A series takes its date and span from its listed dates, first
        to last, so what counts days from the start (checklists) and what
        reads the end (archiving) see the same thing. Nothing listed,
        nothing changes."""
        days = list(self.event_dates.values_list("date", flat=True))
        if not days:
            return
        self.conference_date = self.start_date = days[0]
        self.end_date = days[-1]
        self.save(update_fields=["conference_date", "start_date", "end_date"])


class EventDate(models.Model):
    """A day the edition happens on, for an edition whose days are not a
    run from its start to its end date: a year of meetup nights.

    Listed, the schedule editor offers these days rather than the span,
    and a room may be limited to some of them (``speakers.Room``).
    """

    conference = models.ForeignKey(
        Conference,
        verbose_name="event",
        on_delete=models.CASCADE,
        related_name="event_dates",
    )
    date = models.DateField()
    label = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "date"], name="portal_event_date_per_edition"
            )
        ]

    def __str__(self):
        when = dateformat.format(self.date, "D j M Y")
        return f"{when}, {self.label}" if self.label else when
