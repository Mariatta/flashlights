"""Who the organizer side is made of, and how to name a user.

Shared by forms, filters and template tags so the rule lives in one place.
"""

from django.contrib.auth.models import User
from django.db.models import Q

from common.permissions import users_with_perm
from volunteer.constants import ApplicationStatus

from .constants import LIAISE_PRESENTERS, VIEW_PROGRAM


def user_label(user):
    """Full name, or the username when the profile has none: how a person is
    named in prose, emails and page text."""
    return user.get_full_name() or user.username


def picker_label(user):
    """``Full Name (username)`` for a dropdown, where a name alone is not
    enough to tell two people apart; the username alone when there is no
    name. The same form the team form uses for its leads."""
    name = user.get_full_name()
    return f"{name} ({user.username})" if name else user.username


def organizer_side_candidates(conference):
    """Who may take an organizer item: everyone who reads the program, and
    every approved volunteer of the edition (pending or waitlisted
    volunteers are not offered until they are onboarded)."""
    readers = users_with_perm(VIEW_PROGRAM).values("pk")
    return (
        User.objects.filter(
            Q(pk__in=readers)
            | Q(
                volunteerprofile__conference=conference,
                volunteerprofile__application_status=ApplicationStatus.APPROVED,
            ),
            is_active=True,
        )
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


def liaison_candidates(conference):
    """Who may be set as a presenter's liaison: whoever holds
    ``speakers.liaise_presenters`` (the Organizers, Program and Speaker
    liaisons sets), by team or by group."""
    return users_with_perm(LIAISE_PRESENTERS).order_by(
        "first_name", "last_name", "username"
    )


def assignee_candidates(conference):
    """Who an organizer item may be handed to."""
    return organizer_side_candidates(conference)
