"""Permissions derived from team membership in the active edition.

Design §7.1: teams grant, an auth backend derives. Rather than syncing people
into global ``auth.Group`` rows, which are not per edition and would keep
last year's Sponsorship team in charge until something removed them, this
backend answers ``has_perm`` from the user's approved memberships and
leaderships in the **active** edition's teams. Leads get the lead set on top
of the team set. Nothing is ever stale and the edition switch revokes by
itself.

Baseline grants, computed the same way and tied to no team: an approved
volunteer of the active edition may read sponsors. The speaker side stays
relational (``PresenterRequiredMixin`` asks for a presenter row), as do team
leads, liaisons and item assignees, which is why they are not here.

Superusers keep Django's bypass: ``User.has_perm`` returns True for an
active superuser before any backend is asked.
"""

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import Permission, User
from django.db.models import Q

from portal.models import Conference

from .constants import BASELINE_APPROVED_VOLUNTEER, ApplicationStatus
from .models import VolunteerProfile

# Cached on the user instance for the request, as ModelBackend does with
# ``_perm_cache``; a different name so the two never read each other's.
CACHE_ATTRIBUTE = "_team_perm_cache"


def _labels(permissions):
    return {
        f"{app_label}.{codename}"
        for app_label, codename in permissions.values_list(
            "content_type__app_label", "codename"
        )
    }


class TeamPermissionsBackend(BaseBackend):
    """``has_perm`` through the active edition's teams; nothing to authenticate."""

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()
        if not hasattr(user_obj, CACHE_ATTRIBUTE):
            setattr(user_obj, CACHE_ATTRIBUTE, self._derive(user_obj))
        return getattr(user_obj, CACHE_ATTRIBUTE)

    def _derive(self, user):
        conference = Conference.get_active()
        if conference is None:
            return set()
        profile = VolunteerProfile.objects.filter(
            user=user,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        ).first()
        if profile is None:
            return set()
        granted = set(BASELINE_APPROVED_VOLUNTEER)
        granted |= _labels(
            Permission.objects.filter(
                teams__conference=conference, teams__members=profile
            )
        )
        granted |= _labels(
            Permission.objects.filter(
                lead_teams__conference=conference, lead_teams__team_leads=profile
            )
        )
        return granted

    def has_perm(self, user_obj, perm, obj=None):
        return perm in self.get_all_permissions(user_obj, obj)

    def with_perm(self, perm, is_active=True, include_superusers=True, obj=None):
        """Everyone the active edition's teams grant ``perm`` to.

        The recipient side of the same rule, so "who gets the internal
        notification" finds team members. Django's ``User.objects.with_perm``
        needs ``backend=`` while more than one backend answers; use
        ``common.permissions.users_with_perm`` to ask every backend at once.
        """
        if not isinstance(perm, str) or "." not in perm:
            raise ValueError(
                "Permission name should be in the form app_label.codename."
            )
        if obj is not None:
            return User.objects.none()
        app_label, _, codename = perm.partition(".")
        conference = Conference.get_active()
        query = Q(pk__in=[])
        if conference is not None:
            approved = Q(
                volunteerprofile__conference=conference,
                volunteerprofile__application_status=ApplicationStatus.APPROVED,
            )
            if perm in BASELINE_APPROVED_VOLUNTEER:
                query |= approved
            query |= approved & Q(
                volunteerprofile__teams__conference=conference,
                volunteerprofile__teams__permissions__codename=codename,
                volunteerprofile__teams__permissions__content_type__app_label=app_label,
            )
            query |= approved & Q(
                volunteerprofile__team_leads__conference=conference,
                volunteerprofile__team_leads__lead_permissions__codename=codename,
                volunteerprofile__team_leads__lead_permissions__content_type__app_label=app_label,
            )
        if include_superusers:
            query |= Q(is_superuser=True)
        users = User.objects.filter(query)
        if is_active is not None:
            users = users.filter(is_active=is_active)
        return users.distinct()
