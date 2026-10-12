from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic.edit import FormView

from common.mixins import SuperuserRequiredMixin
from portal.models import Conference

from .forms import TicketingSettingsForm
from .models import POLL_MINUTES, TicketingSettings


class TicketingSettingsView(SuperuserRequiredMixin, FormView):
    """The edition's Tickets page (decision 0012): where registrations come
    from, and how its questions and products map."""

    form_class = TicketingSettingsForm
    template_name = "ticketing/settings_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.conference = get_object_or_404(Conference, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = TicketingSettings.objects.filter(
            conference=self.conference
        ).first() or TicketingSettings(conference=self.conference)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["poll_minutes"] = POLL_MINUTES
        context["webhook_url"] = self.request.build_absolute_uri(
            reverse("speakers:pretix_webhook", args=[self.conference.slug])
        )
        return context

    def form_valid(self, form):
        form.save()
        messages.success(self.request, f"Saved the tickets for {self.conference}.")
        return redirect("conference_edit", pk=self.conference.pk)
