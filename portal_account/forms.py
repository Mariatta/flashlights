from django import forms
from django.forms import ModelForm

from .handles import CHANNELS, HandleFieldsMixin
from .models import PortalProfile


class PortalProfileForm(HandleFieldsMixin, ModelForm):
    """Edit a profile. The two agreement boxes are disabled on purpose: they
    show what was accepted, and accepting happens once, at the gate
    (``portal_account.agreements``), not here. The handles (website,
    GitHub, Discord and the rest) are the person's one record of them,
    which the volunteer and speaker forms share."""

    HANDLE_COLUMNS = {channel.code: channel.code for channel in CHANNELS}
    PRONOUNS_FIELD = "pronouns"

    username = forms.CharField(disabled=True)
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.CharField(disabled=True)
    coc_agreement = forms.BooleanField(disabled=True, required=False)
    tos_agreement = forms.BooleanField(disabled=True, required=False)

    class Meta:
        model = PortalProfile
        fields = ["pronouns", "profile_picture", "coc_agreement", "tos_agreement"]

    def clean(self):
        cleaned_data = super().clean()
        self.instance.username = cleaned_data.get("username")
        self.email = cleaned_data.get("email")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields["username"].initial = self.user.username
            self.fields["email"].initial = self.user.email
            self.fields["first_name"].initial = self.user.first_name
            self.fields["last_name"].initial = self.user.last_name
        for channel in CHANNELS:
            self.fields[channel.code] = forms.CharField(
                required=False,
                label=channel.label,
                help_text=channel.help_text,
                max_length=200,
            )
        self.init_handles(self.user)

        # fix field order
        self.order_fields(
            [
                "username",
                "first_name",
                "last_name",
                "email",
                "pronouns",
                "profile_picture",
                "coc_agreement",
                "tos_agreement",
                *[channel.code for channel in CHANNELS],
            ]
        )

    def handle_fields(self):
        """The handle fields, bound, for the template to list."""
        return [self[channel.code] for channel in CHANNELS]

    def save(self, commit=True):
        """ """
        user = self.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()
        self.instance.user = user
        portal_profile = super().save(commit)
        return portal_profile
