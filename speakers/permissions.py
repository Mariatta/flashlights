"""Read-side predicates for the speaker module (design §7.1, task 3.4).

Running the program is ``speakers.manage_program``, reading it
``speakers.view_program``; the Program team's set carries both, and the
team backend grants them for the active edition. Liaison access is an
object-level check on the data model (``Presenter.liaison``), the same
shape as ``TeamLeadRequiredMixin`` looking at ``team.team_leads``, and so
is carrying an item. The template editor, the guides and the settings
pages gate on their own labels in ``speakers.mixins``.
"""

from django.db.models import Q

from volunteer.constants import ApplicationStatus
from volunteer.models import Team

from .constants import ASSIGN_ITEMS, MANAGE_PROGRAM, VIEW_PROGRAM, ItemOwner
from .models import ChecklistItem, Presenter


def is_speaker_organizer(user):
    """Whether ``user`` may run the program: add sessions, invite, schedule,
    publish, decide proposals (``speakers.manage_program``)."""
    return bool(user.is_authenticated and user.has_perm(MANAGE_PROGRAM))


def can_view_program(user):
    """Whether ``user`` reads every session and presenter of the edition.
    Managing the program implies it."""
    return bool(
        user.is_authenticated
        and (user.has_perm(VIEW_PROGRAM) or user.has_perm(MANAGE_PROGRAM))
    )


def can_assign_items(user):
    """Whether ``user`` may hand an organizer item to someone else."""
    return user.has_perm(ASSIGN_ITEMS)


def is_speaker_liaison(user, conference):
    """Whether ``user`` looks after at least one presenter in ``conference``."""
    if not user.is_authenticated or conference is None:
        return False
    return Presenter.objects.filter(conference=conference, liaison=user).exists()


def can_work_sessions(user, conference):
    """Reads the program, or liaises: may open the organizer side of the
    module. Querysets' ``visible_to`` narrow a liaison to their presenters."""
    return can_view_program(user) or is_speaker_liaison(user, conference)


def approved_teams(user, conference):
    """The edition's teams this user is an approved member of.

    Pending and waitlisted members are not on the team for this purpose:
    being added to a team is not the same as having been onboarded onto it.
    """
    if not user.is_authenticated or conference is None:
        return Team.objects.none()
    return Team.objects.filter(
        conference=conference,
        members__user=user,
        members__application_status=ApplicationStatus.APPROVED,
    )


def owned_by(user, conference):
    """Filter for the organizer items this user carries: assigned to them,
    or to a team they are an approved member of.

    One definition for the three places that must agree: the queue that
    lists the items, the predicate that opens the queue, and the check that
    lets someone act on one. They drifted apart twice; keep them here.
    """
    return Q(assignee=user) | Q(team__in=approved_teams(user, conference))


def is_speaker_assignee(user, conference):
    """Whether ``user`` carries an open organizer item in this edition.

    Organizer items are assigned to any approved volunteer, not only to
    liaisons (``people.organizer_side_candidates``), so carrying one is its
    own reason to reach the queue and tick the item off. It is an
    object-level check on the data, like the liaison one: the assignment is
    the grant.

    An item owned by a team they are an approved member of counts the same:
    the queue lists it and the digest mails it to them.

    Any assigned item counts, not only an open one: ticking off the last
    one would otherwise 403 the very page the volunteer is standing on, and
    they still need the queue to reopen something they closed too early.
    """
    if not user.is_authenticated or conference is None:
        return False
    return ChecklistItem.objects.filter(
        owned_by(user, conference),
        conference=conference,
        owner=ItemOwner.ORGANIZER,
    ).exists()


def can_work_queue(user, conference):
    """Who may open the queue and act on an item: organizers, liaisons, and
    whoever an organizer item was handed to."""
    return can_work_sessions(user, conference) or is_speaker_assignee(user, conference)
