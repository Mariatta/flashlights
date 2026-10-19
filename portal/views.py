from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user
from django.contrib.auth.mixins import PermissionRequiredMixin, UserPassesTestMixin
from django.db.models import Count, ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, TemplateView
from django.views.generic.edit import CreateView, DeleteView, FormView, UpdateView

from attendee.models import PretixOrder
from common.mixins import AdminRequiredMixin, ConferenceAdminRequiredMixin
from portal.common import (
    SPONSOR_AWAITING_INVOICE_STATUS,
    get_historical_comparison_data,
    get_stats_cached_values,
    proposals_received,
)
from portal.constants import (
    CACHE_KEY_ATTENDEE_COUNT,
    CACHE_KEY_ATTENDEE_FIRST_TIME_COUNT,
    CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_DONATIONS_TOTAL_AMOUNT,
    CACHE_KEY_SPONSORSHIP_COMMITTED,
    CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT,
    SPONSORSHIP_GOAL,
)
from portal.forms import ConferenceForm, EventDateForm, StartNewYearForm, VenueForm
from portal.models import Cadence, Conference, EventDate, Venue
from portal.permissions import can_start_next_year, is_organizer
from portal.services import (
    bring_forward_volunteers,
    clone_sponsorship_tiers,
    clone_teams,
)
from speakers.editions import set_working_edition
from speakers.models import Presenter, SpeakerSettings, speaker_module_enabled
from speakers.seeds import clone_speaker_setup, seed_new_edition
from speakers.stats import edition_task_stats
from sponsorship.models import SponsorshipProfile
from ticketing.models import carry_forward
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile


def index(request):
    """
    Send authenticated users to their personalized hub, anonymous visitors to
    the public landing page.

    - Organizers (staff/superuser): the organizer dashboard.
    - Presenters who are not also volunteering this year: their speaker
      dashboard.
    - Everyone else: the volunteer hub (one consistent home, not a second
      landing page), or the public landing page when the instance does not
      run volunteering.
    """
    user = get_user(request)
    if user.is_authenticated:
        active = Conference.get_active()
        # On the program, not merely known to the speakers app: a presenter
        # row alone (a proposal nobody has answered) opens no speaker page,
        # and sending it there would land on a refusal.
        is_presenter = (
            speaker_module_enabled(active)
            and Presenter.objects.filter(conference=active, user=user)
            .onboarded()
            .exists()
        )
        # An account with no profile never reaches this view: the agreement
        # gate (portal_account.agreements) sends it to the page that asks,
        # and creates the profile when it answers.
        if is_organizer(user):
            return redirect("organizer_dashboard")
        if (
            is_presenter
            and not VolunteerProfile.objects.filter(
                user=user, conference=active
            ).exists()
        ):
            return redirect("speakers:my_dashboard")
        if settings.VOLUNTEERING_ENABLED:
            return redirect("volunteer:index")

    return render(request, "portal/index.html")


def _stats_conference(request):
    """Resolve the conference to show stats for from ``?year=``.

    Falls back to the active conference when no (valid) year is given.
    """
    year = request.GET.get("year")
    if year:
        conference = Conference.objects.filter(year=year).first()
        if conference is not None:
            return conference
    return Conference.get_active()


def stats(request):
    """
    Show Interesting Public Stats
    """
    conference = _stats_conference(request)
    context = {
        "stats": get_stats_cached_values(conference),
        "conferences": Conference.objects.all(),
        "selected_conference": conference,
        # Years that predate the portal have no live data, only a snapshot.
        "historical_snapshot": conference.historical_snapshot if conference else None,
        "proposals": proposals_received(conference) if conference else 0,
    }

    return render(request, "portal/stats.html", context)


def stats_json(request):
    """
    Return the stats as a JSON response
    """
    context = {}

    context["stats"] = get_stats_cached_values(_stats_conference(request))

    return JsonResponse(context)


#: Comparison chart -> the setting that makes its numbers meaningful here.
#: A chart not listed (proposals) is always shown.
COMPARISON_CHART_SWITCHES = {
    "registrations_comparison": lambda: PretixOrder.objects.exists(),
    "sponsors_comparison": "SPONSORSHIP_ENABLED",
    "sponsorship_amount_comparison": "SPONSORSHIP_ENABLED",
    "donors_comparison": "SPONSORSHIP_ENABLED",
    "donation_amount_comparison": "SPONSORSHIP_ENABLED",
    "proceeds_comparison": "SPONSORSHIP_ENABLED",
}


def _chart_is_on(chart):
    """A setting name, or a callable for what a setting cannot say (any
    edition has registrations: ticketing is per edition)."""
    setting = COMPARISON_CHART_SWITCHES.get(chart["chart_id"])
    if setting is None:
        return True
    return setting() if callable(setting) else getattr(settings, setting)


def stats_comparison(request):
    """
    Show year-over-year comparison charts across all event editions, each
    chart only where its feature is on for this instance.
    """
    context = {
        "historical_comparison": [
            chart for chart in get_historical_comparison_data() if _chart_is_on(chart)
        ]
    }

    return render(request, "portal/stats_comparison.html", context)


class OrganizerDashboardView(AdminRequiredMixin, TemplateView):
    """Cross-app command center for organizers (``portal.view_organizer_dashboard``).

    A router, not a reimplementation: the top row reuses the same cached stats
    as the public Stats page, and every action/attention item links to the
    existing list views. Nothing here duplicates those surfaces.
    """

    template_name = "portal/organizer_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        conference = Conference.get_active()
        # Stats helpers assume an edition; with none active, fall back to empties
        # so the dashboard renders zeros instead of erroring.
        stats = get_stats_cached_values(conference) if conference else {}
        context["conference"] = conference

        # Top-line cross-app numbers (clean keys for the template).
        context["onboarded_count"] = stats.get(CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT, 0)
        # Goal percentages are raw divisions (can be long decimals and exceed
        # 100% once the goal is beaten). Round for display; cap the bar at 100%.
        sponsorship_percent = stats.get(CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT, 0)
        donation_percent = stats.get(CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT, 0)
        context["sponsorship_goal_percent"] = round(sponsorship_percent)
        context["sponsorship_bar_width"] = min(round(sponsorship_percent), 100)
        context["sponsorship_committed"] = stats.get(CACHE_KEY_SPONSORSHIP_COMMITTED, 0)
        context["sponsorship_goal"] = stats.get(SPONSORSHIP_GOAL, 0)
        context["donation_goal_percent"] = round(donation_percent)
        context["donation_bar_width"] = min(round(donation_percent), 100)
        context["donations_total"] = stats.get(CACHE_KEY_DONATIONS_TOTAL_AMOUNT, 0)
        context["donation_goal"] = conference.donation_goal if conference else 0
        context["attendee_count"] = stats.get(CACHE_KEY_ATTENDEE_COUNT, 0)
        context["attendee_first_time_count"] = stats.get(
            CACHE_KEY_ATTENDEE_FIRST_TIME_COUNT, 0
        )

        # Needs-attention queue - all derivable, no new model fields.
        if conference:
            teams = Team.objects.filter(conference=conference)
            # Count every pending application, whether or not the volunteer
            # picked a team: a team-less applicant still needs review, and is
            # only reachable from the volunteers list (no team dashboard lists
            # them). Counting profiles (not per-team members) also avoids
            # double-counting someone who applied to several teams.
            context["pending_reviews"] = VolunteerProfile.objects.filter(
                conference=conference,
                application_status=ApplicationStatus.PENDING,
            ).count()
            context["unled_teams"] = sum(1 for t in teams if not t.team_leads.exists())
            context["awaiting_invoice"] = SponsorshipProfile.objects.filter(
                conference=conference,
                progress_status__in=SPONSOR_AWAITING_INVOICE_STATUS,
            ).count()
        else:
            context["pending_reviews"] = 0
            context["unled_teams"] = 0
            context["awaiting_invoice"] = 0
        context["pending_status"] = ApplicationStatus.PENDING.value
        # Speaker-portal tasks across the edition, when the module is on.
        context["task_stats"] = (
            edition_task_stats(conference)
            if speaker_module_enabled(conference)
            else None
        )
        return context


def _to_dates_page(request, conference):
    """A series with no dates listed: the Dates page is where to go next."""
    messages.info(request, f"Now list the dates {conference.name} meets on.")
    return reverse("conference_dates", kwargs={"pk": conference.pk})


class StartNewYearView(UserPassesTestMixin, FormView):
    """Guided flow for organizers to stand up the next conference edition
    (``portal.start_next_year``, the Organizers leads' permission).

    Creates the edition and, in one step, carries selected data over from the
    previous edition (teams, sponsorship tiers, goal amounts, returning
    volunteers) and optionally activates it.
    """

    template_name = "portal/start_new_year.html"

    def test_func(self):
        return can_start_next_year(self.request.user)

    form_class = StartNewYearForm
    success_url = reverse_lazy("index")

    def dispatch(self, request, *args, **kwargs):
        if not Conference.can_start_next_year():
            messages.info(
                request,
                "The next edition already exists: plan it from the program "
                "pages, and make it active from its edit page when it is time.",
            )
            return redirect("index")
        return super().dispatch(request, *args, **kwargs)

    def _previous_edition(self):
        return Conference.objects.order_by("-year").first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["source"] = self._previous_edition()
        return context

    def get_success_url(self):
        if self.created.cadence == Cadence.SERIES:
            return _to_dates_page(self.request, self.created)
        return super().get_success_url()

    def form_valid(self, form):
        data = form.cleaned_data
        source = self._previous_edition()

        conference = Conference(year=data["year"], name=data["name"], slug=data["slug"])
        form.apply_dates(conference)
        if source:
            # A community keeps its chat from one edition to the next.
            conference.chat_platform = source.chat_platform
            conference.chat_name = source.chat_name
            conference.chat_url = source.chat_url
        if source and data["copy_goals"]:
            conference.sponsorship_goal = source.sponsorship_goal
            conference.donation_goal = source.donation_goal
        if data["activate"]:
            conference.is_active = True
        conference.save()
        self.created = conference

        carried = []
        if carry_forward(conference, source, data.get("pretix_event_slug") or ""):
            carried.append("the ticketing settings")
        if source:
            if data["clone_teams"]:
                carried.append(f"{clone_teams(conference, source)} team(s)")
            if data["copy_tiers"]:
                carried.append(f"{clone_sponsorship_tiers(conference, source)} tier(s)")
            if data["bring_volunteers"]:
                carried.append(
                    f"{bring_forward_volunteers(conference, source)} volunteer(s)"
                )
        if source and data["copy_speaker_setup"]:
            counts = clone_speaker_setup(
                conference, source, enable=data["speaker_portal"]
            )
            carried.append(
                f"{counts['templates']} checklist template(s), "
                f"{counts['guides']} speaker guide(s), {counts['rooms']} room(s)"
            )
        elif data["speaker_portal"]:
            SpeakerSettings.objects.update_or_create(
                conference=conference, defaults={"speaker_module_enabled": True}
            )
            seed_new_edition(conference)

        if data["speaker_portal"] and not data["activate"]:
            # Created to be planned: the program pages open on it.
            set_working_edition(self.request, conference)
        message = f"Created {conference}."
        if carried:
            message += f" Carried over: {', '.join(carried)}."
        if data["activate"]:
            message += " It is now the active edition."
        if data["speaker_portal"]:
            message += " The speaker portal is on."
            if not data["activate"]:
                message += " The program pages now show it; the public site stays on the active edition."
        messages.success(self.request, message)
        return super().form_valid(form)


class ConferenceList(ConferenceAdminRequiredMixin, ListView):
    model = Conference
    template_name = "portal/conference_list.html"
    context_object_name = "conferences"

    def get_queryset(self):
        # A series shows how many dates it lists.
        return (
            super()
            .get_queryset()
            .select_related("venue")
            .annotate(listed_dates=Count("event_dates"))
        )


class ConferenceUpdate(ConferenceAdminRequiredMixin, UpdateView):
    model = Conference
    form_class = ConferenceForm
    template_name = "portal/conference_form.html"
    success_url = reverse_lazy("conference_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event_dates"] = self.object.event_dates.select_related("venue")
        return context

    def get_success_url(self):
        if self.needs_dates:
            return _to_dates_page(self.request, self.object)
        return super().get_success_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        form.save_dates(self.object)
        return response

    def post(self, request, *args, **kwargs):
        # Read before the save, which may just have made it a series.
        self.needs_dates = (
            request.POST.get("cadence") == Cadence.SERIES
            and not self.get_object().event_dates.exists()
        )
        return super().post(request, *args, **kwargs)


class EventDateMixin(ConferenceAdminRequiredMixin):
    """The Dates pages of one event, a series: its listed dates, each with
    a label and, when it is somewhere else, its own venue."""

    model = EventDate
    pk_url_kwarg = "date_pk"

    def dispatch(self, request, *args, **kwargs):
        self.conference = get_object_or_404(Conference, pk=kwargs["pk"])
        if (
            self.conference.cadence != Cadence.SERIES
            and request.user.is_authenticated
            and self.get_test_func()()
        ):
            messages.info(request, "A once-a-year event's dates are on its edit page.")
            return redirect("conference_edit", pk=self.conference.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return EventDate.objects.filter(conference=self.conference).select_related(
            "venue"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["conference"] = self.conference
        return context

    def get_success_url(self):
        return reverse("conference_dates", kwargs={"pk": self.conference.pk})

    def changed(self, verb, row):
        # The event's date and span follow the list.
        self.conference.span_from_dates()
        messages.success(self.request, f"{verb} {row}.")


class EventDateFormMixin(EventDateMixin):
    """Adding and editing: the form knows its event."""

    form_class = EventDateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["conference"] = self.conference
        return kwargs


class EventDateList(EventDateFormMixin, CreateView):
    """The dates, and the form that adds one."""

    template_name = "portal/event_dates.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event_dates"] = self.get_queryset()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.changed("Added", self.object)
        return response


class EventDateUpdate(EventDateFormMixin, UpdateView):
    template_name = "portal/event_date_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        self.changed("Saved", self.object)
        return response


class EventDateDelete(EventDateMixin, DeleteView):
    """Removes a date; the button on the Dates page posts here. A session
    scheduled on it stays reachable in the editor, on its day."""

    http_method_names = ["post"]

    def form_valid(self, form):
        response = super().form_valid(form)
        self.changed("Removed", self.object)
        return response


class VenueList(ConferenceAdminRequiredMixin, ListView):
    """The instance's places, each with what points at it."""

    model = Venue
    template_name = "portal/venue_list.html"
    context_object_name = "venues"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                editions_count=Count("editions", distinct=True),
                dates_count=Count("event_dates", distinct=True),
                rooms_count=Count("rooms", distinct=True),
            )
        )


class VenueCreate(ConferenceAdminRequiredMixin, CreateView):
    model = Venue
    form_class = VenueForm
    template_name = "portal/venue_form.html"
    success_url = reverse_lazy("venue_list")


class VenueUpdate(ConferenceAdminRequiredMixin, UpdateView):
    model = Venue
    form_class = VenueForm
    template_name = "portal/venue_form.html"
    success_url = reverse_lazy("venue_list")


class VenueDelete(ConferenceAdminRequiredMixin, DeleteView):
    model = Venue
    template_name = "portal/venue_confirm_delete.html"
    context_object_name = "venue"
    success_url = reverse_lazy("venue_list")

    def form_valid(self, form):
        # An edition, a date or a room still points at it: PROTECTed.
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f"Cannot delete {self.object}: an event, a date or a room still "
                "uses it. Point those elsewhere first.",
            )
            return redirect("venue_list")


class ConferenceDelete(PermissionRequiredMixin, DeleteView):
    # Deleting an edition is the Organizers leads' alone, not every editor's.
    permission_required = "portal.delete_conference"
    model = Conference
    template_name = "portal/conference_confirm_delete.html"
    context_object_name = "conference"
    success_url = reverse_lazy("conference_list")

    def form_valid(self, form):
        # An edition referenced by teams/profiles/sponsors/tiers/donations is
        # PROTECTed; surface a clear message instead of a 500.
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f"Cannot delete {self.object}: it still has teams, volunteers, "
                "sponsors, tiers, or donations. Remove those first.",
            )
            return redirect("conference_list")
