from django import forms
from django.contrib import admin

from .models import TicketingSettings


class TicketingSettingsAdminForm(forms.ModelForm):
    """The token and the webhook secret are write-only: encrypted at rest,
    never echoed back. Leave a field blank to keep what is stored."""

    api_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current token.",
    )
    webhook_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current secret.",
    )

    class Meta:
        model = TicketingSettings
        fields = "__all__"

    def _keep_when_blank(self, name):
        value = self.cleaned_data.get(name)
        return value if value else getattr(self.instance, name)

    def clean_api_token(self):
        return self._keep_when_blank("api_token")

    def clean_webhook_secret(self):
        return self._keep_when_blank("webhook_secret")


@admin.register(TicketingSettings)
class TicketingSettingsAdmin(admin.ModelAdmin):
    form = TicketingSettingsAdminForm
    list_display = ("conference", "provider", "organizer", "event_id", "last_synced_at")
    list_select_related = ("conference",)
    readonly_fields = ("last_synced_at",)
