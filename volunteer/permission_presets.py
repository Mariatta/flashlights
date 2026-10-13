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

# The catalogue in plain words, grouped for the pickers on the team form and
# the lists on the team and profile pages. Order is display order.
CATALOGUE = {
    "Conferences": {
        "portal.view_organizer_dashboard": "Open the Organize dashboard",
        "portal.add_conference": "Add editions",
        "portal.change_conference": "Edit editions",
        "portal.delete_conference": "Delete editions",
        "portal.start_next_year": "Start the next edition",
    },
    "Volunteers": {
        "volunteer.view_volunteerprofile": "See volunteers and their profiles",
        "volunteer.review_volunteerprofile": "Review volunteer applications",
        "volunteer.add_team": "Add teams",
        "volunteer.change_team": "Edit teams",
        "volunteer.delete_team": "Delete teams",
        "volunteer.receive_volunteer_notifications": (
            "Receive the internal volunteer emails"
        ),
    },
    "Sponsorship": {
        "sponsorship.view_sponsorshipprofile": "See sponsors",
        "sponsorship.add_sponsorshipprofile": "Add sponsors",
        "sponsorship.change_sponsorshipprofile": "Edit sponsors",
        "sponsorship.delete_sponsorshipprofile": "Delete sponsors",
        "sponsorship.send_invoice": "Send sponsor invoices",
        "sponsorship.view_unconfirmed_sponsors": "See sponsors not yet confirmed",
        "sponsorship.add_sponsorshiptier": "Add sponsorship tiers",
        "sponsorship.change_sponsorshiptier": "Edit sponsorship tiers",
        "sponsorship.delete_sponsorshiptier": "Delete sponsorship tiers",
        "sponsorship.receive_sponsorship_notifications": (
            "Receive the internal sponsorship emails"
        ),
    },
    "Speakers": {
        "speakers.manage_program": "Manage the program",
        "speakers.view_program": "See every session and presenter",
        "speakers.change_checklisttemplate": "Edit the checklist templates",
        "speakers.change_handbook": "Edit the speaker guides",
        "speakers.change_speakersettings": (
            "Change the speaker settings, types, roles and readiness gates"
        ),
        "speakers.assign_checklistitem": "Reassign checklist items",
        "speakers.liaise_presenters": "Be a presenter's liaison",
    },
}


def grouped_choices():
    """The catalogue as grouped form choices: ``[(group, [(label, words)])]``."""
    return [(group, list(labels.items())) for group, labels in CATALOGUE.items()]


def plain_label(label):
    """The words for one ``app.codename``; the codename when it is not
    in the catalogue (a built-in permission granted by hand)."""
    for labels in CATALOGUE.values():
        if label in labels:
            return labels[label]
    return label


def describe(permissions):
    """``[(group, [words])]`` for a set of ``Permission`` rows, in catalogue
    order, with anything outside the catalogue under "Other"."""
    held = {label_of(p) for p in permissions.select_related("content_type")}
    groups = []
    for group, labels in CATALOGUE.items():
        words = [text for label, text in labels.items() if label in held]
        if words:
            groups.append((group, words))
        held -= set(labels)
    if held:
        groups.append(("Other", sorted(held)))
    return groups


def presets_as_json():
    """The presets for the team form's script: name -> the two label lists."""
    return {
        name: {"members": list(preset.members), "leads": list(preset.leads)}
        for name, preset in PRESETS.items()
    }


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
