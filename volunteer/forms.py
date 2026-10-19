from django import forms
from django.forms import ModelForm
from django.forms.widgets import SelectMultiple
from django.utils.safestring import mark_safe

from common.tasks import enqueue
from portal.models import Conference
from portal_account.handles import VOLUNTEER_COLUMNS, HandleFieldsMixin

from .constants import ApplicationStatus
from .models import Language, Team, VolunteerProfile
from .organizers import may_change_grants
from .permission_presets import (
    ORGANIZERS,
    PRESETS,
    grouped_choices,
    label_of,
    permissions_for,
)
from .tasks import (
    send_internal_volunteer_onboarding_email_task,
    send_volunteer_onboarding_email_task,
)


class SelectMultipleWidget(SelectMultiple):
    """
    A custom widget for selecting multiple values with autocomplete.
    """

    def __init__(self, attrs=None, choices=()):
        default_attrs = {
            "class": "form-control select2-multiple",
            "data-placeholder": "Start typing to select ...",
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs, choices)


class VolunteerProfileForm(HandleFieldsMixin, ModelForm):
    """The application and the volunteer's own edit form. The handles
    (GitHub, Discord and the rest) are the person's, kept on the account
    and shared with the speaker side (``portal_account.handles``)."""

    HANDLE_COLUMNS = VOLUNTEER_COLUMNS

    github_username = forms.CharField(
        required=True,
        max_length=39,
        help_text="Required - Your GitHub username (e.g., username). Organizers use it to give you access to the team's repositories.",
        label="GitHub Username",
        error_messages={"required": "GitHub username is required."},
    )
    additional_comments = forms.CharField(widget=forms.Textarea, required=False)
    teams = forms.ModelMultipleChoiceField(
        required=False,
        queryset=Team.objects.filter(open_to_new_members=True),
        widget=forms.CheckboxSelectMultiple,
        help_text=mark_safe(
            "Each team's description says what it does."
            "<br>Only teams that are open to new members are shown."
            "If the team is not listed, it means that it is now full and no longer accepting new members."
        ),
        label="Which teams are you interested in joining?",
    )

    class Meta:
        model = VolunteerProfile
        # conference is not shown in the form: new profiles are tied to the
        # active conference automatically in save().
        # The chapter and the region are PyLadies notions the model keeps
        # and the form hides.
        exclude = [
            "user",
            "application_status",
            "languages_spoken",
            "conference",
            "chapter",
            "region",
        ]
        help_texts = {
            "github_username": "Required - Your GitHub username (e.g., username). Organizers use it to give you access to the team's repositories.",
            "discord_username": "Required - Your Discord username for team communication (e.g., username or username#1234)",
            "instagram_username": "Instagram username without @ (e.g., username)",
            "bluesky_username": "Bluesky username (e.g., username or username.bsky.social)",
            "mastodon_url": "Mastodon handle (e.g., @username@instance.tld or https://instance.tld/@username)",
            "x_username": "X/Twitter username without @ (e.g., username)",
            "linkedin_url": "LinkedIn URL (e.g., linkedin.com/in/username)",
            "availability_hours_per_week": "Our volunteers are expected to commit at least 1 hour per week until the event day."
            "By sharing your availability, we can better match you with tasks and teams.",
        }
        labels = {
            "availability_hours_per_week": "What is your volunteering availability?",
        }

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        languages = [
            (lang.id, lang.name) for lang in Language.objects.all().order_by("name")
        ]

        # The active edition says whether there is a Discord
        # to ask about; another platform or none asks nothing.
        active = Conference.get_active()
        if active is not None and not active.uses_discord:
            del self.fields["discord_username"]
        else:
            self.fields["discord_username"].required = True
        self.fields["language"].widget = SelectMultipleWidget(
            choices=languages,
            attrs={
                "data-placeholder": "Start typing to select languages...",
            },
        )
        # Teams are conference-scoped: only offer the active edition's open
        # teams, never a prior year's.
        self.fields["teams"].queryset = Team.objects.filter(
            open_to_new_members=True, conference=Conference.get_active()
        )

        # The handles come from the person's record, whichever form they
        # gave them on; a brand-new application also brings forward the
        # availability and languages of the most recent prior profile.
        self.init_handles(self.user)
        if self.user and not (self.instance and self.instance.pk):
            self._prefill_from_prior_profile()

    PREFILL_FIELDS = ("availability_hours_per_week",)

    def _prefill_from_prior_profile(self):
        prior = (
            VolunteerProfile.objects.filter(user=self.user)
            .exclude(conference=Conference.get_active())
            .order_by("-conference__year")
            .first()
        )
        if prior is not None:
            for field in self.PREFILL_FIELDS:
                self.initial.setdefault(field, getattr(prior, field))
            self.initial.setdefault("language", list(prior.language.all()))

    def save(self, commit=True):
        if self.user:
            self.instance.user = self.user

        # A new application belongs to the active conference edition.
        if self.instance.conference_id is None:
            self.instance.conference = Conference.get_active()

        volunteer_profile = super().save(commit)
        return volunteer_profile


class VolunteerProfileReviewForm(ModelForm):

    additional_comments = forms.CharField(widget=forms.Textarea, required=False)
    teams = forms.ModelMultipleChoiceField(
        required=True,
        # Scoped to the reviewed profile's edition in __init__; an empty default
        # avoids ever offering another year's teams.
        queryset=Team.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Please assign at least one team."},
    )

    class Meta:
        model = VolunteerProfile
        fields = ["teams"]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Assign only teams belonging to the profile's own conference edition.
        if self.instance and self.instance.conference_id:
            teams = Team.objects.filter(conference_id=self.instance.conference_id)
            # Joining Organizers grants what Organizers hold: only they
            # bring someone onto it.
            if self.user is not None and not may_change_grants(self.user):
                teams = teams.exclude(short_name=ORGANIZERS)
            self.fields["teams"].queryset = teams

    def clean(self):
        cleaned_data = super().clean()
        if self.user is not None and self.instance.user_id == self.user.pk:
            raise forms.ValidationError(
                "You cannot review your own application: ask another reviewer."
            )
        return cleaned_data

    def save(self, commit=True):
        newly_approved = False
        if self.instance.application_status in (
            ApplicationStatus.PENDING,
            ApplicationStatus.WAITLISTED,
        ):
            self.instance.application_status = ApplicationStatus.APPROVED
            newly_approved = True
        volunteer_profile = super().save(commit)

        if newly_approved:
            enqueue(send_volunteer_onboarding_email_task, volunteer_profile.id)
            enqueue(send_internal_volunteer_onboarding_email_task, volunteer_profile.id)
        return volunteer_profile


class TeamLeadChoiceField(forms.ModelMultipleChoiceField):
    """Label team-lead options by full name, falling back to username."""

    def label_from_instance(self, obj):
        name = obj.user.get_full_name()
        return f"{name} ({obj.user.username})" if name else obj.user.username


class TeamForm(ModelForm):
    """Create/edit a team through the portal (instead of Django admin).

    What the team grants is picked here: two
    checkbox lists grouped by app in plain words, and a preset that fills
    them, in the browser as it is chosen or on save when nothing was
    ticked. The sets are written by ``save``; the model's own fields go
    through ``Meta``.
    """

    team_leads = TeamLeadChoiceField(
        queryset=VolunteerProfile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    preset = forms.ChoiceField(
        required=False,
        label="Start from preset",
        choices=[("", "Pick the permissions yourself")]
        + [(name, name) for name in PRESETS],
        help_text=(
            "Fills the two lists below with the usual set for that team; "
            "adjust them afterwards."
        ),
    )
    permissions = forms.MultipleChoiceField(
        required=False,
        label="Team permissions",
        choices=grouped_choices,
        widget=forms.CheckboxSelectMultiple,
        help_text="What every approved member of the team may do.",
    )
    lead_permissions = forms.MultipleChoiceField(
        required=False,
        label="Lead permissions",
        choices=grouped_choices,
        widget=forms.CheckboxSelectMultiple,
        help_text="What the team leads may do on top of the team permissions.",
    )

    class Meta:
        model = Team
        fields = [
            "conference",
            "short_name",
            "description",
            "open_to_new_members",
            "team_leads",
        ]
        help_texts = {
            "description": (
                "Markdown supported: headings, lists, links, **bold**, "
                "and *italics*."
            ),
        }

    def __init__(self, *args, conference=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # The edition the team belongs to is now chosen on the form, so it works
        # even when no edition is active. Default a new team to the caller's hint
        # (the active edition).
        if not self.instance.pk and conference is not None:
            self.fields["conference"].initial = conference

        # Team leads must be volunteers of the *team's own* edition. Scope the
        # options to the conference in play: the submitted one on a bound form,
        # else the instance's, else the caller's hint.
        lead_conference = conference
        if self.is_bound:
            selected = self.data.get("conference")
            lead_conference = (
                Conference.objects.filter(pk=selected).first() if selected else None
            )
        elif self.instance.pk:
            lead_conference = self.instance.conference
        self.fields["team_leads"].queryset = VolunteerProfile.objects.filter(
            conference=lead_conference
        ).select_related("user")

        if self.instance.pk:
            self.initial.setdefault(
                "permissions", [label_of(p) for p in self.instance.permissions.all()]
            )
            self.initial.setdefault(
                "lead_permissions",
                [label_of(p) for p in self.instance.lead_permissions.all()],
            )

        # What a team may do, and who leads Organizers, are the Organizers
        # team's to change: anyone else who edits teams would otherwise grant
        # themselves through their own team. Disabled fields keep what is
        # stored whatever is posted.
        if user is not None and not may_change_grants(user):
            del self.fields["preset"]
            for name in ("permissions", "lead_permissions"):
                self.fields[name].disabled = True
                self.fields[name].help_text = (
                    "Only the Organizers team changes what a team may do."
                )
            if self.instance.short_name == ORGANIZERS:
                self.fields["team_leads"].disabled = True

    def clean(self):
        cleaned = super().clean()
        preset = PRESETS.get(cleaned.get("preset") or "")
        # A preset chosen with nothing ticked is the no-script path of the
        # form: fill both lists from it.
        if (
            preset
            and not cleaned.get("permissions")
            and not cleaned.get("lead_permissions")
        ):
            cleaned["permissions"] = list(preset.members)
            cleaned["lead_permissions"] = list(preset.leads)
        return cleaned

    def save(self, commit=True):
        team = super().save(commit=commit)
        if commit:
            self.save_permissions(team)
        return team

    def save_permissions(self, team):
        team.permissions.set(permissions_for(self.cleaned_data["permissions"]))
        team.lead_permissions.set(
            permissions_for(self.cleaned_data["lead_permissions"])
        )
