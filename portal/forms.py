from allauth.account.forms import LoginForm as AllauthLoginForm
from allauth.account.forms import SignupForm
from captcha.conf import settings as captcha_settings
from captcha.fields import CaptchaField, CaptchaTextInput
from django import forms
from django.apps import apps

from portal.models import Conference


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


class StartNewYearForm(forms.Form):
    """Create a new conference edition and carry over from the previous one."""

    year = forms.IntegerField(min_value=2000, label="Year")
    name = forms.CharField(max_length=100, label="Name")
    slug = forms.SlugField(label="Slug")
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        label="Start date",
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        label="End date",
    )
    conference_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        label="Event date",
    )
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


class ConferenceForm(forms.ModelForm):
    """Edit an existing conference edition through the portal.

    ``speaker_module_enabled`` is not a Conference field: it lives on the
    edition's ``speakers.SpeakerSettings`` row, which this form reads and
    writes so the switch sits with the other per-edition flags. The field
    disappears when the speakers app is not installed.
    """

    speaker_module_enabled = forms.BooleanField(
        required=False,
        label="Speaker portal enabled",
        help_text="Turn on sessions, presenters, invitations and checklists "
        "for this edition.",
    )
    # Decision 0013: the format lives on the speaker settings row but is
    # chosen here, where the edition's dates and venue are.
    event_format = forms.ChoiceField(
        required=False,
        label="Format",
        help_text="How sessions happen. In person leaves out the online-only "
        "parts of the speaker portal (pre-recording, premieres, tech checks); "
        "hybrid keeps everything, chosen per session.",
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
            "pretix_event_slug",
            "sponsorship_goal",
            "donation_goal",
            "proposals_count",
            "start_date",
            "end_date",
            "conference_date",
            "venue_name",
            "venue_address",
            "venue_url",
            "banner_text",
            "sponsors_url",
            "coc_url",
            "donate_url",
            "schedule_url",
        ]
        labels = {
            "is_active": "Active edition",
            "volunteer_application_open": "Taking volunteer applications",
            "sponsorship_open": "Taking sponsors",
            "accepting_donations": "Taking donations",
        }
        help_texts = {
            "volunteer_application_open": "Advertises volunteering on the landing "
            "page and opens volunteer sign-up for this edition. Off, the public "
            "page says nothing about volunteering and the team keeps its hub.",
            "venue_name": "Shown with the dates on the landing page and the "
            "public program. Leave blank for an online edition.",
        }
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "conference_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "venue_address": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        model = _speaker_settings_model()
        if model is None:
            del self.fields["speaker_module_enabled"]
            del self.fields["event_format"]
            return
        format_field = model._meta.get_field("event_format")
        self.fields["event_format"].choices = format_field.choices
        self.fields["event_format"].initial = format_field.default
        if self.instance.pk:
            settings_row = model.objects.filter(conference=self.instance).first()
            self.fields["speaker_module_enabled"].initial = bool(
                settings_row and settings_row.speaker_module_enabled
            )
            if settings_row:
                self.fields["event_format"].initial = settings_row.event_format

    def save(self, commit=True):
        conference = super().save(commit=commit)
        model = _speaker_settings_model()
        if model is None:
            return conference
        enabled = self.cleaned_data.get("speaker_module_enabled", False)
        default_format = model._meta.get_field("event_format").default
        event_format = self.cleaned_data.get("event_format") or default_format
        settings_row = model.objects.filter(conference=conference).first()
        if settings_row is None:
            # A row only once there is something to keep: the module on, or
            # a format other than the default.
            if enabled or event_format != default_format:
                model.objects.create(
                    conference=conference,
                    speaker_module_enabled=enabled,
                    event_format=event_format,
                )
            return conference
        changed = []
        if settings_row.speaker_module_enabled != enabled:
            settings_row.speaker_module_enabled = enabled
            changed.append("speaker_module_enabled")
        if settings_row.event_format != event_format:
            settings_row.event_format = event_format
            changed.append("event_format")
        if changed:
            settings_row.save(update_fields=changed + ["modified_date"])
        return conference
