"""Default permission sets for teams (design §7.1).

A preset is what the portal admin starts a team from; every team's set stays
editable afterwards. Labels are ``app.codename``; ``permissions_for`` turns
them into rows. The Organizers set is also written literally into the data
migration that builds the first Organizers team, because a migration must
stay replayable when this module has moved on.
"""

from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from django.contrib.auth.models import Permission
from django.db.models import Q

ORGANIZERS = "Organizers"


@dataclass(frozen=True)
class Preset:
    members: tuple
    leads: tuple = field(default_factory=tuple)


ORGANIZER_MEMBER_PERMISSIONS = (
    "portal.view_organizer_dashboard",
    "portal.add_conference",
    "portal.change_conference",
    "volunteer.view_volunteerprofile",
    "volunteer.review_volunteerprofile",
    "volunteer.add_team",
    "volunteer.change_team",
    "volunteer.delete_team",
    "volunteer.receive_volunteer_notifications",
    "sponsorship.view_sponsorshipprofile",
    "sponsorship.add_sponsorshipprofile",
    "sponsorship.change_sponsorshipprofile",
    "sponsorship.delete_sponsorshipprofile",
    "sponsorship.send_invoice",
    "sponsorship.view_unconfirmed_sponsors",
    "sponsorship.add_sponsorshiptier",
    "sponsorship.change_sponsorshiptier",
    "sponsorship.delete_sponsorshiptier",
    "sponsorship.receive_sponsorship_notifications",
    "speakers.manage_program",
    "speakers.view_program",
    "speakers.change_checklisttemplate",
    "speakers.change_handbook",
    "speakers.change_speakersettings",
    "speakers.assign_checklistitem",
    "speakers.liaise_presenters",
)

PRESETS = {
    ORGANIZERS: Preset(
        members=ORGANIZER_MEMBER_PERMISSIONS,
        leads=("portal.delete_conference", "portal.start_next_year"),
    ),
    "Volunteer coordination": Preset(
        members=(
            "volunteer.view_volunteerprofile",
            "volunteer.review_volunteerprofile",
            "volunteer.add_team",
            "volunteer.change_team",
            "volunteer.delete_team",
            "volunteer.receive_volunteer_notifications",
        )
    ),
    "Sponsorship": Preset(
        members=(
            "sponsorship.add_sponsorshipprofile",
            "sponsorship.change_sponsorshipprofile",
            "sponsorship.delete_sponsorshipprofile",
            "sponsorship.send_invoice",
            "sponsorship.view_unconfirmed_sponsors",
            "sponsorship.add_sponsorshiptier",
            "sponsorship.change_sponsorshiptier",
            "sponsorship.delete_sponsorshiptier",
            "sponsorship.receive_sponsorship_notifications",
        )
    ),
    "Program": Preset(
        members=(
            "speakers.manage_program",
            "speakers.view_program",
            "speakers.assign_checklistitem",
            "speakers.liaise_presenters",
            "speakers.change_checklisttemplate",
            "speakers.change_handbook",
        ),
        leads=("speakers.change_speakersettings",),
    ),
    "Speaker liaisons": Preset(
        members=("speakers.liaise_presenters", "speakers.assign_checklistitem")
    ),
    # The media-asset permissions join this set with task 3.7, once the
    # MediaAsset model exists.
    "Design": Preset(
        members=("speakers.view_program",), leads=("speakers.assign_checklistitem",)
    ),
}


def permissions_for(labels):
    """The ``Permission`` rows for ``app.codename`` labels, as a queryset."""
    labels = list(labels)
    if not labels:
        return Permission.objects.none()
    clauses = []
    for label in labels:
        app_label, _, codename = label.partition(".")
        clauses.append(Q(content_type__app_label=app_label, codename=codename))
    return Permission.objects.filter(reduce(or_, clauses)).select_related(
        "content_type"
    )


def label_of(permission):
    """``app.codename`` for a ``Permission`` row."""
    return f"{permission.content_type.app_label}.{permission.codename}"
