from django.conf import settings
from django.utils.functional import SimpleLazyObject

from attendee.models import PretixOrder
from portal.permissions import can_manage_conferences, can_start_next_year, is_organizer
from portal_account.permissions import is_maintainer
from ticketing.models import is_set_up
from volunteer.models import VolunteerProfile

from .models import Conference


def active_conference(request):
    """Expose the active conference to all templates as ``active_conference``."""
    return {"active_conference": Conference.get_active()}


def features(request):
    """The instance's feature switches, for the nav, rails, landing page and
    stats sections (``portal/settings.py``, "Feature switches").

    * ``volunteering_enabled``: the Volunteer hub exists on this instance
    * ``sponsorship_enabled``: sponsors, tiers and donations do
    * ``stats_public``: the public stats pages are served
    * ``pretix_configured``: attendee numbers can exist: the active edition
      has ticketing set up, or registrations already
    """
    return {
        "volunteering_enabled": settings.VOLUNTEERING_ENABLED,
        "sponsorship_enabled": settings.SPONSORSHIP_ENABLED,
        "stats_public": settings.STATS_PUBLIC,
        "pretix_configured": SimpleLazyObject(_attendees_on),
    }


def _attendees_on():
    active = Conference.get_active()
    return bool(
        is_set_up(active) or PretixOrder.objects.filter(conference=active).exists()
    )


def user_capabilities(request):
    """Expose permission flags to every template so the nav is consistent.

    The nav lives in ``portal/base.html`` and therefore renders on every page,
    but ``volunteer_profile`` is only set by the handful of views that bother
    to. Without this processor the sponsorship nav check silently collapses to
    superuser-only everywhere else. Computing the flags here fixes that and
    gives every template one vocabulary:

    * ``is_organizer``          — holds ``portal.view_organizer_dashboard``
      (matches AdminRequiredMixin)
    * ``can_manage_sponsorship``— holds ``sponsorship.change_sponsorshipprofile``
    * ``can_view_sponsorship``  — holds ``sponsorship.view_sponsorshipprofile``,
      which every approved volunteer of the edition gets as a baseline
    * ``active_volunteer_profile`` — this user's profile for the active edition
    * ``leads_any_team``        — true if they lead at least one team.
      Nothing reads it today (My teams left the tabs for the personal rail),
      so it is lazy: the query runs when a template asks, and not otherwise
    * ``can_manage_conferences``— holds ``portal.change_conference`` (matches
      the Conference views' ConferenceAdminRequiredMixin)
    * ``can_start_next_year``   — holds ``portal.start_next_year`` AND a new
      edition can be started;
      the shared Organize rail renders on every organizer page, so the flag
      must be available everywhere, not just in the views that used to pass it
    * ``is_maintainer``         - holds ``portal_account.view_maintenance``;
      independent of organizer status (see MaintainerRequiredMixin)
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {
            "is_organizer": False,
            "can_manage_sponsorship": False,
            "can_view_sponsorship": False,
            "active_volunteer_profile": None,
            "leads_any_team": False,
            "can_manage_conferences": False,
            "can_start_next_year": False,
            "is_maintainer": False,
        }

    profile = VolunteerProfile.objects.filter(
        user=user, conference=Conference.get_active()
    ).first()
    # An instance without sponsorship has nobody who can see or manage it,
    # so every rail and page reading these flags goes quiet together.
    sponsorship = settings.SPONSORSHIP_ENABLED

    return {
        "is_organizer": is_organizer(user),
        # Read from the permissions the Sponsorship set grants. Reading
        # sponsors is the backend's baseline for every approved volunteer of
        # the edition.
        "can_manage_sponsorship": sponsorship
        and user.has_perm("sponsorship.change_sponsorshipprofile"),
        "can_view_sponsorship": sponsorship
        and user.has_perm("sponsorship.view_sponsorshipprofile"),
        "active_volunteer_profile": profile,
        # Lazy on purpose: no template reads it since My teams left the
        # tabs for the personal rail, and a plain bool here would run its
        # query on every authenticated page for nobody.
        "leads_any_team": SimpleLazyObject(
            lambda: bool(profile and profile.team_leads.exists())
        ),
        "can_manage_conferences": can_manage_conferences(user),
        "can_start_next_year": (
            can_start_next_year(user) and Conference.can_start_next_year()
        ),
        "is_maintainer": is_maintainer(user),
    }
