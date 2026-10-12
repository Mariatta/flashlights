from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic.edit import FormView

from common.mixins import SuperuserRequiredMixin
from portal.models import Conference

from .forms import CsvImportForm, TicketingSettingsForm
from .models import POLL_MINUTES, TicketingSettings, ticketing_for
from .sync import CsvImportError, import_csv


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


class CsvImportView(SuperuserRequiredMixin, FormView):
    """Upload an export of the edition's registrations (decision 0012)."""

    form_class = CsvImportForm
    template_name = "ticketing/csv_import.html"

    def dispatch(self, request, *args, **kwargs):
        self.conference = get_object_or_404(Conference, pk=kwargs["pk"])
        self.ticketing = ticketing_for(self.conference)
        if self.ticketing is None or not self.ticketing.csv_columns.get("email"):
            messages.info(request, "Map the CSV columns on the Tickets page first.")
            return redirect("conference_tickets", pk=self.conference.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        context["columns"] = self.ticketing.csv_columns
        return context

    def form_valid(self, form):
        try:
            result = import_csv(self.ticketing, form.cleaned_data["file"].read())
        except CsvImportError as exc:
            form.add_error("file", str(exc))
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Imported {result.imported} row(s), {result.registered} registered.",
        )
        for line, reason in result.skipped[:10]:
            messages.warning(self.request, f"Line {line} skipped: {reason}.")
        if len(result.skipped) > 10:
            messages.warning(
                self.request, f"{len(result.skipped) - 10} more line(s) skipped."
            )
        return redirect("conference_tickets_import", pk=self.conference.pk)
