"""View gates shared across apps, on ``has_perm`` (design §7.1).

Each mixin reads a named predicate from the owning app's ``permissions.py``;
teams grant the permission through ``volunteer.auth_backends``. Object-level
access (the owner of a profile, the lead of a team) stays a data check.
"""

from django.contrib.auth.mixins import UserPassesTestMixin

from portal.permissions import can_manage_conferences, is_organizer
from portal_account.permissions import is_maintainer
from volunteer.models import Team, VolunteerProfile
from volunteer.permissions import can_review_volunteers, can_view_volunteers, leads_team


class AdminRequiredMixin(UserPassesTestMixin):
    """The Organize surface: ``portal.view_organizer_dashboard``."""

    def test_func(self):
        return is_organizer(self.request.user)


class MaintainerRequiredMixin(UserPassesTestMixin):
    """Mixin for the Maintenance section (infra, not conference organizing).

    Gated on the ``portal_account.view_maintenance`` permission, which the
    "Infra maintainers" group grants. Independent of organizer status: a
    person can hold either, or both.
    """

    def test_func(self):
        return is_maintainer(self.request.user)


class ConferenceAdminRequiredMixin(UserPassesTestMixin):
    """The editions themselves: ``portal.change_conference``."""

    def test_func(self):
        return can_manage_conferences(self.request.user)


class VolunteerOrAdminRequiredMixin(UserPassesTestMixin):
    """The owner of the profile in the URL, or someone who reviews volunteers.

    For views where users act on their own application unless they run the
    volunteer side.
    """

    def test_func(self):
        pk = self.kwargs.get("pk")
        instance = VolunteerProfile.objects.filter(pk=pk).first()
        is_owner = bool(instance and instance.user == self.request.user)
        return is_owner or can_review_volunteers(self.request.user)


class TeamLeadRequiredMixin(UserPassesTestMixin):
    """Mixin for views scoped to a single team in the URL (``pk``).

    Access is granted to whoever may see volunteers and to a lead of *that*
    team. A team lead only reaches the teams they actually lead, never every
    team; that half is relational and stays so.
    """

    def get_team(self):
        return Team.objects.filter(pk=self.kwargs.get("pk")).first()

    def is_team_lead(self, team):
        return leads_team(self.request.user, team)

    def test_func(self):
        if can_view_volunteers(self.request.user):
            return True
        return self.is_team_lead(self.get_team())
