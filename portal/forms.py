from allauth.account.forms import LoginForm as AllauthLoginForm
from allauth.account.forms import SignupForm
from captcha.conf import settings as captcha_settings
from captcha.fields import CaptchaField, CaptchaTextInput
from django import forms
from django.apps import apps
from django.forms import inlineformset_factory
from django.utils.module_loading import import_string

from portal.models import Cadence, Conference, EventDate


class PortalCaptchaTextInput(CaptchaTextInput):
    """The package widget with a visible, labelled audio alternative."""

    template_name = "portal/widgets/captcha.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Intrinsic size on the <img> so the form does not shift as it loads.
        context["image_width"], context["image_height"] = (
            captcha_settings.CAPTCHA_IMAGE_SIZE
        )
        return context


class CustomSignupForm(SignupForm):
    first_name = forms.CharField(
        max_length=200,
        label="First Name",
        widget=forms.TextInput(attrs={"placeholder": "First Name"}),
    )
    last_name = forms.CharField(
        max_length=200,
        label="Last Name",
        widget=forms.TextInput(attrs={"placeholder": "Last Name"}),
    )
    coc_agreement = forms.BooleanField(
        required=True,
        label="I agree to the Code of Conduct",
        help_text="You must agree to our Code of Conduct to use this site.",
    )
    tos_agreement = forms.BooleanField(
        required=True,
        label="I agree to the Terms of Service",
        help_text="You must agree to our Terms of Service to use this site.",
    )
    captcha = CaptchaField(
        label="Verification",
        help_text="Type the characters shown in the image.",
        widget=PortalCaptchaTextInput(
            attrs={"class": "form-control", "autocomplete": "off"}
        ),
    )

    def save(self, request):
        user = super().save(request)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()

        from portal_account.models import PortalProfile

        portal_profile, created = PortalProfile.objects.get_or_create(user=user)
        portal_profile.coc_agreement = self.cleaned_data.get("coc_agreement", False)
        portal_profile.tos_agreement = self.cleaned_data.get("tos_agreement", False)
        portal_profile.save()

        return user


class EventDateForm(forms.ModelForm):
    """One listed date of a series: the day and an optional label."""

    class Meta:
        model = EventDate
        fields = ["date", "label"]
        widgets = {
            "date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"
            ),
            "label": forms.TextInput(
                attrs={
                    "placeholder": "Label, if you like: February workshop",
                    "class": "form-control",
                }
            ),
        }


class BaseEventDateFormSet(forms.BaseInlineFormSet):
    """The listed dates of a series, one row each, added one at a time.
    ``require`` is on when the edition is a series, which needs at least
    one; once a year the rows are not read at all."""

    def __init__(self, *args, require=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require = require

    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.fields["DELETE"].widget.attrs["class"] = "form-check-input"

    def listed(self):
        """The dates of the rows that stay, once every row is valid."""
        return [
            form.cleaned_data["date"]
            for form in self.forms
            if form.cleaned_data.get("date") and not form.cleaned_data.get("DELETE")
        ]

    def clean(self):
        # A date listed twice is the inline formset's own unique check.
        super().clean()
        if self.require and not any(self.errors) and not self.listed():
            raise forms.ValidationError("List at least one date it meets on.")


#: One blank row to start with; the page adds more without a round trip.
EventDateFormSet = inlineformset_factory(
    Conference,
    EventDate,
    form=EventDateForm,
    formset=BaseEventDateFormSet,
    extra=1,
    can_delete=True,
)


class EditionDatesForm(forms.Form):
    """What kind of event an edition is, and the dates that answer asks
    for. The edition form and the form that starts the next edition both
    build on it, so they ask the same and save the same way.

    Once a year: the event date, and the last day when it runs over
    several; the start date mirrors the event date, so the schedule offers
    that run. A series: the dates it meets on, one row each in an
    ``EventDateFormSet`` beside this form, and the edition's date and span
    follow them (``Conference.span_from_dates``). Either way an edition
    without a date is refused, which is what used to leave the schedule
    offering every day of a year.
    """

    cadence = forms.ChoiceField(
        choices=Cadence.choices,
        initial=Cadence.ONCE,
        label="What kind of event",
        help_text="Decides which dates are asked for. The dates can be "
        "changed any time.",
    )
    conference_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        label="Event date",
        help_text="The day it happens, or the first day of a run of days.",
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        label="Last day",
        help_text="Only when it runs over several days.",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("cadence") == Cadence.ONCE:
            day, last = cleaned.get("conference_date"), cleaned.get("end_date")
            if not day and "conference_date" not in self.errors:
                self.add_error("conference_date", "When does it happen?")
            elif day and last and last < day:
                self.add_error("end_date", "The last day is before the event date.")
        return cleaned

    def dates_valid(self, formset):
        """Once a year does not read the rows; a series needs them valid."""
        return self.cleaned_data.get("cadence") == Cadence.ONCE or formset.is_valid()

    def apply_dates(self, conference):
        """Before the edition is saved: its cadence and, once a year, its
        date and span from the answers."""
        data = self.cleaned_data
        conference.cadence = data["cadence"]
        if conference.cadence == Cadence.ONCE:
            day = data["conference_date"]
            conference.conference_date = conference.start_date = day
            conference.end_date = data.get("end_date") or day

    def save_dates(self, conference, formset):
        """After the edition is saved: once a year keeps no listed dates,
        so rows from before go; a series saves its rows (a row edited in
        place keeps its id, so the rooms tied to it stay tied) and takes
        its date and span from them."""
        if conference.cadence == Cadence.ONCE:
            conference.event_dates.all().delete()
            return
        formset.instance = conference
        formset.save()
        conference.span_from_dates()


class StartNewYearForm(EditionDatesForm):
    """Create a new conference edition and carry over from the previous one."""

    year = forms.IntegerField(min_value=2000, label="Year")
    name = forms.CharField(max_length=100, label="Name")
    slug = forms.SlugField(label="Slug")
    pretix_event_slug = forms.CharField(
        required=False, max_length=100, label="Pretix event slug"
    )
    clone_teams = forms.BooleanField(
        required=False, initial=True, label="Clone teams from the previous edition"
    )
    copy_tiers = forms.BooleanField(
        required=False, initial=True, label="Copy sponsorship tiers"
    )
    copy_goals = forms.BooleanField(
        required=False, initial=True, label="Copy goal amounts"
    )
    bring_volunteers = forms.BooleanField(
        required=False, label="Bring forward approved volunteers (as pending)"
    )
    copy_speaker_setup = forms.BooleanField(
        required=False,
        initial=True,
        label="Copy the speaker portal setup (checklist templates, guides, settings)",
    )
    speaker_portal = forms.BooleanField(
        required=False,
        label="Enable the speaker portal for this edition",
        help_text="Can be switched later on the event edit form.",
    )
    activate = forms.BooleanField(required=False, label="Activate this edition now")

    def clean_year(self):
        year = self.cleaned_data["year"]
        if Conference.objects.filter(year=year).exists():
            raise forms.ValidationError("An event for that year already exists.")
        return year

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        if Conference.objects.filter(slug=slug).exists():
            raise forms.ValidationError("An event with that slug already exists.")
        return slug


def _speaker_settings_model():
    """The speakers app's settings model, or None when it is not installed.

    Every other dependency in the portal runs speakers -> portal. This form
    is the one place that needs to read the other way, so it looks the model
    up through the app registry rather than importing it: the core app keeps
    working without the feature module, and there is no import to untangle
    if the two ever have to load in the other order.
    """
    if not apps.is_installed("speakers"):
        return None
    return apps.get_model("speakers", "SpeakerSettings")


class LoginForm(AllauthLoginForm):
    """allauth's sign-in form with the remember-me label in sentence case."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "remember" in self.fields:
            self.fields["remember"].label = "Remember me"


class ConferenceForm(EditionDatesForm, forms.ModelForm):
    """Edit an existing conference edition through the portal.

    ``speaker_module_enabled`` is not a Conference field: it lives on the
    edition's ``speakers.SpeakerSettings`` row, which this form reads and
    writes so the switch sits with the other per-edition flags. The field
    disappears when the speakers app is not installed. The dates come
    from ``EditionDatesForm``, whose fields stand in for the model's.
    """

    speaker_module_enabled = forms.BooleanField(
        required=False,
        label="Speaker portal enabled",
        help_text="Turn on sessions, presenters, invitations and checklists "
        "for this edition.",
    )
    # The format lives on the speaker settings row but is
    # chosen here, where the edition's dates and venue are.
    event_format = forms.ChoiceField(
        required=False,
        label="Format",
        help_text="How sessions happen. In person leaves out the online-only "
        "parts of the speaker portal (pre-recording, premieres, tech checks); "
        "hybrid keeps everything, chosen per session.",
    )
    recordings = forms.ChoiceField(
        required=False,
        label="Recordings",
        help_text="None: no files and no post-production. The team records: "
        "the team uploads each session's recording after the event. Speakers "
        "pre-record: they upload before the event (online and hybrid only).",
    )

    class Meta:
        model = Conference
        # The switches sit together (the form renders them as one group).
        fields = [
            "year",
            "name",
            "slug",
            "is_active",
            "volunteer_application_open",
            "sponsorship_open",
            "accepting_donations",
            "sponsorship_goal",
            "donation_goal",
            "proposals_count",
            "cadence",
            "conference_date",
            "end_date",
            "venue_name",
            "venue_address",
            "venue_url",
            "chat_platform",
            "chat_name",
            "chat_url",
            "reply_to_email",
            "banner_text",
            "sponsors_url",
            "coc_url",
            "donate_url",
            "schedule_url",
        ]
        labels = {
            "proposals_count": "Proposals received elsewhere",
            "is_active": "Active edition",
            "volunteer_application_open": "Taking volunteer applications",
            "sponsorship_open": "Taking sponsors",
            "accepting_donations": "Taking donations",
        }
        help_texts = {
            "proposals_count": "Only if your call for proposals ran outside "
            "this portal: how many you received. Leave at 0 and the stats count "
            "the proposals sent here.",
            "volunteer_application_open": "Advertises volunteering on the landing "
            "page and opens volunteer sign-up for this edition. Off, the public "
            "page says nothing about volunteering and the team keeps its hub.",
            "venue_name": "Shown with the dates on the landing page and the "
            "public program. Leave blank for an online edition.",
            "chat_url": "The invite link speakers and volunteers are pointed "
            "to. Leave blank to point them at the guide instead.",
        }
        widgets = {"venue_address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Which edition is active decides whose team grants count, so
        # switching it is the year rollover's call (portal.start_next_year,
        # the Organizers leads), not every editor's: one tick by someone
        # else would take everyone's access with it.
        if user is not None and not user.has_perm("portal.start_next_year"):
            self.fields["is_active"].disabled = True
            self.fields["is_active"].help_text = (
                "Only the Organizers leads switch the active edition."
            )
        model = _speaker_settings_model()
        if model is None:
            del self.fields["speaker_module_enabled"]
            del self.fields["event_format"]
            del self.fields["recordings"]
            return
        for name in ("event_format", "recordings"):
            field = model._meta.get_field(name)
            self.fields[name].choices = field.choices
            self.fields[name].initial = field.default
        if self.instance.pk:
            settings_row = model.objects.filter(conference=self.instance).first()
            self.fields["speaker_module_enabled"].initial = bool(
                settings_row and settings_row.speaker_module_enabled
            )
            if settings_row:
                self.fields["event_format"].initial = settings_row.event_format
                self.fields["recordings"].initial = settings_row.recordings

    def clean(self):
        cleaned = super().clean()
        model = _speaker_settings_model()
        if model is None:
            return cleaned
        formats = model._meta.get_field("event_format")
        modes = model._meta.get_field("recordings")
        if cleaned.get("chat_platform") == "OTHER" and not cleaned.get("chat_name"):
            self.add_error("chat_name", "Name the platform (Slack, Zulip, Matrix...).")
        in_person = (cleaned.get("event_format") or formats.default) == "IN_PERSON"
        if in_person and (cleaned.get("recordings") or modes.default) == "SPEAKERS":
            self.add_error(
                "recordings",
                "Speakers do not pre-record for an in-person edition: pick "
                '"The team records" or "No recordings".',
            )
        return cleaned

    def save(self, commit=True):
        # The listed dates of a series are the view's: they come as a
        # formset beside this form (``save_dates``).
        self.apply_dates(self.instance)
        conference = super().save(commit=commit)
        model = _speaker_settings_model()
        if model is None:
            return conference
        enabled = self.cleaned_data.get("speaker_module_enabled", False)
        values = {"speaker_module_enabled": enabled}
        defaults = {}
        for name in ("event_format", "recordings"):
            defaults[name] = model._meta.get_field(name).default
            values[name] = self.cleaned_data.get(name) or defaults[name]
        settings_row = model.objects.filter(conference=conference).first()
        if settings_row is None:
            # A row only once there is something to keep: the module on, or
            # a choice other than the default.
            if enabled or any(values[n] != defaults[n] for n in defaults):
                model.objects.create(conference=conference, **values)
        else:
            changed = [n for n, v in values.items() if getattr(settings_row, n) != v]
            for name in changed:
                setattr(settings_row, name, values[name])
            if changed:
                settings_row.save(update_fields=changed + ["modified_date"])
        if enabled:
            # Its checklists, on the format and recordings just saved.
            import_string("speakers.seeds.seed_new_edition")(conference)
        return conference
