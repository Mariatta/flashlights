# Permissions: Who May Do What (Architecture)

This document describes how access is granted and read in the portal since
Stage 3 of the speaker-portal work: the permission catalogue, the team
permission sets and their presets, the authentication backend that derives
a person's permissions from their teams, and how to add a permission. It is
the reference for any work that touches `volunteer/auth_backends.py`,
`volunteer/permission_presets.py`, an app's `permissions.py`, or a
`Meta.permissions` block. The reasoning behind the design is in the speaker
portal architecture document, section 7.1.

## The rule

Every "may this person do this" check goes through Django permissions:
`user.has_perm("app.codename")` in Python, wrapped in a named predicate in
the owning app's `permissions.py`, and `{% if perms.app.codename %}` in
templates. Nothing reads `is_staff`. The flag survives for one purpose,
signing in to the Django admin, and `is_superuser` keeps Django's built-in
bypass as break-glass.

Two things are deliberately not permissions, because they are relations in
the data: leading a particular team (`team.team_leads`), and looking after a
particular presenter (`Presenter.liaison`), carrying an item (`assignee` or
an owning team), or being the presenter yourself. Those stay object-level
checks beside the permission checks.

## The catalogue

Custom permissions are declared in `Meta.permissions` on the model that
owns the feature; the built-in `add`, `change`, `delete` and `view` ones
are reused where they fit. `volunteer.permission_presets.CATALOGUE` carries
the same labels in plain words, grouped by app, and is what the pickers and
the pages show.

| Area | Permission | Grants |
|---|---|---|
| Conferences | `portal.view_organizer_dashboard` | the Organize dashboard and rail |
| | `portal.add_conference`, `change_conference`, `delete_conference` | the edition pages |
| | `portal.start_next_year` | the year rollover |
| Volunteers | `volunteer.view_volunteerprofile` | the volunteers list and other people's profiles |
| | `volunteer.review_volunteerprofile` | approving, waitlisting, re-sending onboarding |
| | `volunteer.add_team`, `change_team`, `delete_team` | the team pages |
| | `volunteer.receive_volunteer_notifications` | the internal volunteer emails |
| Sponsorship | `sponsorship.view_sponsorshipprofile` | reading sponsors (the baseline for every approved volunteer) |
| | `sponsorship.add/change/delete_sponsorshipprofile` | managing sponsors |
| | `sponsorship.send_invoice` | the invoice request |
| | `sponsorship.view_unconfirmed_sponsors` | sponsors whose status is not yet a commitment |
| | `sponsorship.add/change/delete_sponsorshiptier` | the tier pages |
| | `sponsorship.receive_sponsorship_notifications` | the internal sponsorship emails |
| Speakers | `speakers.manage_program` | sessions, invitations, presenters, proposals, the pretix link |
| | `speakers.view_program` | reading every session and presenter (managing implies it) |
| | `speakers.change_checklisttemplate` | the checklist template editor |
| | `speakers.change_handbook` | the speaker guides |
| | `speakers.change_speakersettings` | types, roles, readiness gates, the settings row |
| | `speakers.assign_checklistitem` | handing an organizer item to someone else |
| | `speakers.liaise_presenters` | being offered as a presenter's liaison |
| Maintenance | `portal_account.view_maintenance` | the Maintenance section (granted by a group, not a team) |

The media-asset and promo-asset permissions join the catalogue with the
media pipeline (task 3.7).

## Teams grant

A `Team` carries two sets of `auth.Permission` rows: `permissions`, for
every approved member, and `lead_permissions`, which the team leads hold on
top. Both are edited on the team form in the portal as grouped checkbox
lists in plain words, with a "Start from preset" select that fills them.
The team page lists what the team may do, and a person's volunteer profile
page lists what they hold and where each grant comes from. Start next year
clones both sets with the teams.

The presets, in `volunteer.permission_presets.PRESETS`:

| Team | Members | Leads add |
|---|---|---|
| Organizers | every catalogue permission except the two below | `delete_conference`, `start_next_year` |
| Volunteer coordination | view and review volunteers, manage teams, volunteer notifications | |
| Sponsorship | sponsor add/change/delete, send invoice, unconfirmed statuses, tiers, sponsorship notifications | |
| Program | manage and view the program, assign items, liaise, templates, guides | `change_speakersettings` |
| Speaker liaisons | liaise presenters, assign items | |
| Design | view the program (media permissions arrive with task 3.7) | assign items |

A team with no set at all is still a team: work reaches it through task
assignment, which is relational.

## A backend derives

`volunteer.auth_backends.TeamPermissionsBackend`, third in
`AUTHENTICATION_BACKENDS`, authenticates nobody. It answers
`get_all_permissions` from the user's approved memberships and leaderships
in the **active** edition's teams, plus one baseline tied to no team: an
approved volunteer of the active edition may read sponsors
(`volunteer.constants.BASELINE_APPROVED_VOLUNTEER`). The result is cached
on the user instance for the request. It also answers `with_perm`, so
recipient queries find team members.

Because the backend reads the active edition, the edition switch revokes by
itself: last year's Sponsorship team grants nothing today, and with no
edition active only a superuser reaches Organize. That is the reason the
grants are not synced into global `auth.Group` rows.

Groups still exist for capabilities that outlive an edition. Today that is
Infra maintainers. The Django admin's group page offers members as a
side-by-side box limited to this year's approved, verified volunteers plus
the current members, and labels a member who no longer qualifies, so a
group can be reviewed and pruned from its own page.

Django's `User.objects.with_perm` refuses to answer while more than one
backend can, so recipient queries go through
`common.permissions.users_with_perm`, which asks Django's backend and the
team backend together.

## Adding a permission

1. Declare it in `Meta.permissions` on the model that owns the feature, and
   write the migration.
2. Add its label and plain wording to `CATALOGUE`, and to the presets whose
   teams should carry it. Add the same label to the literal list in the
   next data migration only if a seeded team must gain it on deploy.
3. Add a named predicate to the app's `permissions.py` and read it from the
   view (Django's `PermissionRequiredMixin` with the label, or the
   predicate in `test_func`) and from the template (`perms.app.codename`).
4. Test the grant through a preset team (`join_team` in the root conftest),
   the denial for someone without it, and that a staff flag alone opens
   nothing.

## What went away

The volunteer `Role` model and `VolunteerProfile.roles` (the `RoleTypes` enum stays in `volunteer/constants.py` only because the first migration seeds from it). Roles
granted no access; the Admin and Staff ones routed the internal emails and
picked the organizer variant of the onboarding email, both of which read
permissions now. The migration that removed them put every Admin and Staff
holder on their edition's Organizers team first. Rosters, profiles and
emails show teams and a Lead badge instead.
