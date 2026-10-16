"""A person's handles, kept once on the account.

The volunteer and speaker sides each ask for GitHub, Discord, Mastodon and
the rest, in their own columns, per edition. Here the person has one
record of them (``Handle``, one row per channel), every form that asks
reads and writes that record, and the role rows (``VolunteerProfile``,
``Presenter``) are copies written from it, so everything that prints a
volunteer or a presenter keeps reading its own columns.

The catalogue below names the channels, how each is checked and how it
is stored (Mastodon and LinkedIn as URLs, whatever was typed). Which
channels an edition asks for is not configurable yet; the volunteer
application requires GitHub, and Discord when the edition's chat is
Discord, as it always did.
"""

import re
from typing import NamedTuple

from django import forms
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from portal.validators import validate_discord_username, validate_linked_in_pattern

GITHUB_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$")
INSTAGRAM_RE = re.compile(r"^[a-zA-Z0-9._]{1,30}$")
BLUESKY_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,28}[a-zA-Z0-9](\.[a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})?$"
)
MASTODON_HANDLE_RE = re.compile(
    r"^@(?P<user>[a-zA-Z0-9_]+)@(?P<host>[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$"
)
MASTODON_URL_RE = re.compile(
    r"^https?://[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/@[a-zA-Z0-9_]+$"
)
X_RE = re.compile(r"^[a-zA-Z0-9_]{1,15}$")


def _github(value):
    if not GITHUB_RE.match(value):
        raise ValidationError(
            "GitHub username can only contain alphanumeric characters and hyphens, "
            "cannot start or end with a hyphen, and must be between 1-39 characters."
        )
    return value


def _discord(value):
    validate_discord_username(value)
    return value


def _instagram(value):
    if not INSTAGRAM_RE.match(value):
        raise ValidationError(
            "Instagram username can only contain alphanumeric characters, "
            "periods, and underscores, and must be between 1-30 characters."
        )
    return value


def _bluesky(value):
    if not BLUESKY_RE.match(value):
        raise ValidationError(
            "Invalid Bluesky username format. "
            "Should be either a simple username or a full handle (e.g., username.bsky.social)."
        )
    return value


def _mastodon(value):
    """``@user@instance.tld`` is accepted and stored as the profile URL."""
    handle = MASTODON_HANDLE_RE.match(value)
    if handle:
        return f"https://{handle['host']}/@{handle['user']}"
    if not MASTODON_URL_RE.match(value):
        raise ValidationError(
            "Invalid Mastodon URL format. "
            "Should be either @username@instance.tld or https://instance.tld/@username."
        )
    return value


def _x(value):
    if not X_RE.match(value):
        raise ValidationError(
            "X/Twitter username can only contain alphanumeric characters and underscores, "
            "and must be between 1-15 characters."
        )
    return value


def _linkedin(value):
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    if not validate_linked_in_pattern(value):
        raise ValidationError(
            "Invalid LinkedIn URL format. "
            "Example: linkedin.com/in/username or https://www.linkedin.com/in/username."
        )
    return value


def _website(value):
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    URLValidator()(value)
    return value


class Channel(NamedTuple):
    code: str
    label: str
    help_text: str
    max_length: int
    clean: callable
    #: Printed on the public program when the presenter is public.
    public: bool


#: Website first, then the handles, in the order every form shows them.
CHANNELS = (
    Channel("website", "Website", "Your own site or blog.", 200, _website, True),
    Channel(
        "github",
        "GitHub username",
        "Your GitHub username (e.g., username), without @.",
        39,
        _github,
        True,
    ),
    Channel(
        "discord",
        "Discord username",
        "Your Discord username (e.g., username), for the event's Discord. "
        "Never shown on the public site.",
        32,
        _discord,
        False,
    ),
    Channel(
        "mastodon",
        "Mastodon",
        "Mastodon handle (e.g., @username@instance.tld or "
        "https://instance.tld/@username).",
        100,
        _mastodon,
        True,
    ),
    Channel(
        "bluesky",
        "Bluesky username",
        "Bluesky username (e.g., username or username.bsky.social).",
        100,
        _bluesky,
        True,
    ),
    Channel(
        "linkedin",
        "LinkedIn",
        "LinkedIn URL (e.g., linkedin.com/in/username).",
        100,
        _linkedin,
        True,
    ),
    Channel(
        "instagram",
        "Instagram username",
        "Instagram username without @ (e.g., username).",
        30,
        _instagram,
        False,
    ),
    Channel(
        "x",
        "X username",
        "X/Twitter username without @ (e.g., username).",
        15,
        _x,
        False,
    ),
)
BY_CODE = {channel.code: channel for channel in CHANNELS}
CHANNEL_CHOICES = [(channel.code, channel.label) for channel in CHANNELS]

#: The role rows' columns, by channel: what ``push_handles`` writes.
VOLUNTEER_COLUMNS = {
    "github": "github_username",
    "discord": "discord_username",
    "instagram": "instagram_username",
    "bluesky": "bluesky_username",
    "mastodon": "mastodon_url",
    "x": "x_username",
    "linkedin": "linkedin_url",
}
PRESENTER_COLUMNS = {
    "website": "website_url",
    "github": "github_username",
    "mastodon": "mastodon_url",
    "linkedin": "linkedin_url",
    "bluesky": "bluesky_username",
    "discord": "discord_username",
}


def clean_handle(code, value):
    """``value`` checked and in its stored form for channel ``code``;
    blank stays blank. Raises ``ValidationError`` with the channel's
    message."""
    value = (value or "").strip()
    if not value:
        return ""
    channel = BY_CODE[code]
    value = channel.clean(value)
    if len(value) > channel.max_length:
        raise ValidationError(f"At most {channel.max_length} characters.")
    return value


def _handle_model():
    return apps.get_model("portal_account", "Handle")


def _profiles():
    return apps.get_model("portal_account", "PortalProfile").objects


def _presenters():
    return apps.get_model("speakers", "Presenter").objects


#: ``Presenter.pronouns`` is shorter than the account's.
PRESENTER_PRONOUNS_LENGTH = 50


def pronouns_of(user):
    """The person's pronouns: the account's, else what their newest
    presenter row says (an account not yet onboarded has no profile)."""
    user_id = getattr(user, "pk", user)
    if user_id is None:
        return ""
    stored = _profiles().filter(user_id=user_id).values_list("pronouns", flat=True)
    return (
        stored.first()
        or _presenters()
        .filter(user_id=user_id)
        .exclude(pronouns="")
        .order_by("-conference__year", "-id")
        .values_list("pronouns", flat=True)
        .first()
        or ""
    )


def save_pronouns(user, value):
    """Write the person's pronouns to their account, when they have one,
    and to every presenter row of theirs. A presenter linked but not yet
    onboarded has no account; onboarding creates it from the row."""
    value = (value or "").strip()
    _profiles().filter(user=user).update(pronouns=value)
    _push_pronouns(user, value)


def _push_pronouns(user, value):
    value = value[:PRESENTER_PRONOUNS_LENGTH]
    for presenter in _presenters().filter(user=user).exclude(pronouns=value):
        presenter.pronouns = value
        presenter.save(update_fields=["pronouns", "modified_date"])


def _role_rows(user_id):
    """The person's volunteer profiles then presenters, newest edition
    first, each with its column map."""
    volunteers = apps.get_model("volunteer", "VolunteerProfile").objects
    presenters = apps.get_model("speakers", "Presenter").objects
    rows = [
        (row, VOLUNTEER_COLUMNS)
        for row in volunteers.filter(user_id=user_id).order_by(
            "-conference__year", "-id"
        )
    ]
    rows += [
        (row, PRESENTER_COLUMNS)
        for row in presenters.filter(user_id=user_id).order_by(
            "-conference__year", "-id"
        )
    ]
    return rows


def handles_from_roles(user_id):
    """What the person's role rows say, newest first and the volunteer
    side first, blanks filled from older rows: the record a person has
    before they ever save one, and what the migration started from."""
    found = {}
    for row, columns in _role_rows(user_id):
        for code, column in columns.items():
            value = getattr(row, column) or ""
            if value and not found.get(code):
                found[code] = value
    return found


def handles_of(user):
    """The person's handles as ``{code: value}``, blanks left out. A
    person with no record yet reads as their role rows say, so a profile
    seeded or imported outside the forms still shows."""
    user_id = getattr(user, "pk", user)
    if user_id is None:
        return {}
    stored = dict(
        _handle_model().objects.filter(user_id=user_id).values_list("channel", "value")
    )
    return stored or handles_from_roles(user_id)


def save_handles(user, values):
    """Write ``values`` (``{code: value}``) into the person's record: a
    blank removes the channel, a channel not named is left alone. Then the
    role rows take the record."""
    Handle = _handle_model()
    for code, value in values.items():
        if value:
            Handle.objects.update_or_create(
                user=user, channel=code, defaults={"value": value}
            )
        else:
            Handle.objects.filter(user=user, channel=code).delete()
    push_handles(user)


def adopt_role_handles(user):
    """Fill the blanks of the person's record from their role rows, then
    let the record rule the rows: for an account just linked to a
    presenter an organizer typed in by hand."""
    Handle = _handle_model()
    have = set(Handle.objects.filter(user=user).values_list("channel", flat=True))
    for code, value in handles_from_roles(user.pk).items():
        if code not in have:
            Handle.objects.create(user=user, channel=code, value=value)
    profile = _profiles().filter(user=user).first()
    if profile is not None and not profile.pronouns:
        _profiles().filter(pk=profile.pk).update(pronouns=pronouns_of(user))
    push_handles(user)


def push_handles(user):
    """Write the person's record into every volunteer profile and
    presenter row of theirs. Volunteer rows are updated in place without
    signals (a changed handle is not a new application); presenter rows
    save through their receivers, since the public program shows them."""
    user_id = getattr(user, "pk", user)
    stored = dict(
        _handle_model().objects.filter(user_id=user_id).values_list("channel", "value")
    )
    # Pronouns ride along: the account's, once there is an account.
    found = list(
        _profiles().filter(user_id=user_id).values_list("pronouns", flat=True)[:1]
    )
    pronouns = found[0] if found else None
    if not stored and pronouns is None:
        return
    if stored:
        volunteers = apps.get_model("volunteer", "VolunteerProfile").objects
        volunteers.filter(user_id=user_id).update(
            **{
                column: stored.get(code, "")
                for code, column in VOLUNTEER_COLUMNS.items()
            }
        )
    for presenter in _presenters().filter(user_id=user_id):
        changed = []
        columns = PRESENTER_COLUMNS.items() if stored else []
        wanted = [(column, stored.get(code, "")) for code, column in columns]
        if pronouns is not None:
            wanted.append(("pronouns", (pronouns or "")[:PRESENTER_PRONOUNS_LENGTH]))
        for column, value in wanted:
            if getattr(presenter, column) != value:
                setattr(presenter, column, value)
                changed.append(column)
        if changed:
            presenter.save(update_fields=changed + ["modified_date"])


class HandleFieldsMixin:
    """For a form over a role row whose fields are that row's handle
    columns: the fields start from the person's record, each value is
    checked by its channel, and saving writes the record back.

    ``HANDLE_COLUMNS`` maps channel codes to the form's field names;
    ``PRONOUNS_FIELD`` names the pronouns field, which follows the same
    rule (the account's pronouns are the record). ``handle_user`` names
    the person; ``None`` (a presenter with no account yet) leaves the
    record alone and the row keeps what was typed.
    """

    HANDLE_COLUMNS = {}
    PRONOUNS_FIELD = None

    def init_handles(self, user):
        # Every handle field is plain text: the catalogue checks it and
        # puts it in its stored form (``@user@instance`` becomes a URL), so
        # a model URLField's own check, and the browser's, must not run
        # first. What the model field said about the field is kept.
        for field in self.HANDLE_COLUMNS.values():
            old = self.fields.get(field)
            if old is not None:
                self.fields[field] = forms.CharField(
                    required=old.required,
                    label=old.label,
                    help_text=old.help_text,
                    max_length=old.max_length or 200,
                    error_messages=old.error_messages,
                    empty_value=getattr(old, "empty_value", ""),
                )
        self.handle_user = user if getattr(user, "pk", None) else None
        if self.handle_user is None:
            return
        for code, value in handles_of(self.handle_user).items():
            field = self.HANDLE_COLUMNS.get(code)
            if field in self.fields:
                self.initial[field] = value
        if self.PRONOUNS_FIELD in self.fields:
            pronouns = pronouns_of(self.handle_user)
            if pronouns:
                self.initial[self.PRONOUNS_FIELD] = pronouns

    def clean(self):
        cleaned = super().clean()
        for code, field in self.HANDLE_COLUMNS.items():
            if field not in self.fields or field in self.errors:
                continue
            try:
                value = clean_handle(code, cleaned.get(field))
            except ValidationError as error:
                self.add_error(field, error)
            else:
                # A blank keeps the field's own empty value (None on a
                # nullable column, "" elsewhere).
                if value:
                    cleaned[field] = value
        return cleaned

    def handle_values(self):
        """What this form says, by channel, for the fields it has."""
        cleaned = getattr(self, "cleaned_data", {})
        return {
            code: cleaned.get(field) or ""
            for code, field in self.HANDLE_COLUMNS.items()
            if field in self.fields
        }

    def write_handles(self, user=None):
        """Save the form's handles to the person's record (and so to every
        row of theirs). Called by ``save``; a view that saves with
        ``commit=False`` calls it once the row has its user."""
        user = user or self.handle_user
        if user is None:
            return
        save_handles(user, self.handle_values())
        if self.PRONOUNS_FIELD in self.fields:
            save_pronouns(user, self.cleaned_data.get(self.PRONOUNS_FIELD))

    def save(self, commit=True):
        instance = super().save(commit)
        if commit:
            self.write_handles()
        return instance
