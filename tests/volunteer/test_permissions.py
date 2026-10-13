"""Permissions derived from the active edition's teams (design §7.1, task 3.1)."""

import importlib

import pytest
from django.apps import apps
from django.contrib.auth.models import AnonymousUser, Group, User

from common.permissions import users_with_perm
from portal.models import Conference
from volunteer.auth_backends import CACHE_ATTRIBUTE, TeamPermissionsBackend
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile
from volunteer.permission_presets import (
    ORGANIZERS,
    PRESETS,
    label_of,
    permissions_for,
)

migration = importlib.import_module("volunteer.migrations.0016_flashlights_rebrand")

INVOICE = "sponsorship.send_invoice"
UNCONFIRMED = "sponsorship.view_unconfirmed_sponsors"
READ_SPONSORS = "sponsorship.view_sponsorshipprofile"


def volunteer(username, conference, status=ApplicationStatus.APPROVED):
    user = User.objects.create_user(username=username, email=f"{username}@x.org")
    profile = VolunteerProfile.objects.create(
        user=user, conference=conference, application_status=status
    )
    return user, profile


def team(
    conference, name="Sponsorship", members=(), leads=(), grants=(), lead_grants=()
):
    row = Team.objects.create(conference=conference, short_name=name, description=name)
    row.permissions.set(permissions_for(grants))
    row.lead_permissions.set(permissions_for(lead_grants))
    for profile in members:
        profile.teams.add(row)
    for profile in leads:
        profile.teams.add(row)
        row.team_leads.add(profile)
    return row


def fresh(user):
    """The user as the next request sees them: no permission cache."""
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestHasPerm:
    def test_membership_grants_the_team_set(self, conference):
        user, profile = volunteer("sam", conference)
        team(conference, members=[profile], grants=[INVOICE], lead_grants=[UNCONFIRMED])
        assert user.has_perm(INVOICE)
        assert not user.has_perm(UNCONFIRMED)
        assert user.get_all_permissions() >= {INVOICE, READ_SPONSORS}

    def test_lead_gets_the_lead_set_on_top(self, conference):
        user, profile = volunteer("lee", conference)
        team(conference, leads=[profile], grants=[INVOICE], lead_grants=[UNCONFIRMED])
        assert user.has_perm(INVOICE) and user.has_perm(UNCONFIRMED)

    def test_only_approved_people_count(self, conference):
        pending, pending_profile = volunteer(
            "pen", conference, ApplicationStatus.PENDING
        )
        team(
            conference,
            members=[pending_profile],
            leads=[pending_profile],
            grants=[INVOICE],
            lead_grants=[UNCONFIRMED],
        )
        assert not pending.has_perm(INVOICE) and not pending.has_perm(UNCONFIRMED)
        assert not pending.has_perm(READ_SPONSORS)

    def test_baseline_for_an_approved_volunteer(self, conference):
        user, _ = volunteer("vol", conference)
        assert user.has_perm(READ_SPONSORS)
        assert not user.has_perm(INVOICE)
        nobody = User.objects.create_user(username="nobody")
        assert not nobody.has_perm(READ_SPONSORS)

    def test_the_grant_ends_when_the_edition_changes(self, conference):
        user, profile = volunteer("sam", conference)
        team(conference, members=[profile], grants=[INVOICE])
        assert user.has_perm(INVOICE)
        Conference.objects.create(year=2026, name="2026", slug="2026", is_active=True)
        assert not fresh(user).has_perm(INVOICE)
        assert not fresh(user).has_perm(READ_SPONSORS)

    def test_no_active_edition_grants_nothing(self, conference):
        user, profile = volunteer("sam", conference)
        team(conference, members=[profile], grants=[INVOICE])
        Conference.objects.update(is_active=False)
        assert not fresh(user).has_perm(INVOICE)

    def test_inactive_anonymous_and_object_level_get_nothing(self, conference):
        user, profile = volunteer("sam", conference)
        row = team(conference, members=[profile], grants=[INVOICE])
        backend = TeamPermissionsBackend()
        assert backend.get_all_permissions(AnonymousUser()) == set()
        assert backend.get_all_permissions(user, obj=row) == set()
        assert not backend.has_perm(user, INVOICE, obj=row)
        user.is_active = False
        assert backend.get_all_permissions(user) == set()

    def test_cached_on_the_instance_for_the_request(self, conference):
        user, profile = volunteer("sam", conference)
        row = team(conference, members=[profile], grants=[INVOICE])
        assert user.has_perm(INVOICE)
        row.permissions.clear()
        assert user.has_perm(INVOICE) and hasattr(user, CACHE_ATTRIBUTE)
        assert not fresh(user).has_perm(INVOICE)

    def test_superusers_keep_the_bypass(self, admin_user):
        assert admin_user.has_perm(INVOICE)
        assert TeamPermissionsBackend().get_all_permissions(admin_user) == set()


@pytest.mark.django_db
class TestWithPerm:
    def test_members_and_leads_of_the_active_edition(self, conference):
        member, member_profile = volunteer("mem", conference)
        lead, lead_profile = volunteer("lead", conference)
        pending, pending_profile = volunteer(
            "pen", conference, ApplicationStatus.PENDING
        )
        team(
            conference,
            members=[member_profile, pending_profile],
            leads=[lead_profile],
            grants=[INVOICE],
            lead_grants=[UNCONFIRMED],
        )
        old = Conference.objects.create(year=2020, name="2020", slug="2020")
        stale, stale_profile = volunteer("stale", old)
        team(old, members=[stale_profile], grants=[INVOICE])
        backend = TeamPermissionsBackend()
        assert set(backend.with_perm(INVOICE)) == {member, lead}
        assert set(backend.with_perm(UNCONFIRMED)) == {lead}
        assert set(backend.with_perm(READ_SPONSORS)) == {member, lead}
        assert set(backend.with_perm(INVOICE, obj=old)) == set()
        assert stale not in backend.with_perm(INVOICE)
        assert pending not in backend.with_perm(INVOICE)

    def test_superusers_inactive_accounts_and_bad_names(self, conference, admin_user):
        member, profile = volunteer("mem", conference)
        team(conference, members=[profile], grants=[INVOICE])
        member.is_active = False
        member.save()
        backend = TeamPermissionsBackend()
        assert set(backend.with_perm(INVOICE)) == {admin_user}
        assert set(backend.with_perm(INVOICE, include_superusers=False)) == set()
        assert set(
            backend.with_perm(INVOICE, is_active=None, include_superusers=False)
        ) == {member}
        with pytest.raises(ValueError):
            backend.with_perm("send_invoice")
        Conference.objects.update(is_active=False)
        assert set(backend.with_perm(INVOICE, include_superusers=False)) == set()

    def test_users_with_perm_asks_every_backend(self, conference, admin_user):
        member, profile = volunteer("mem", conference)
        team(conference, members=[profile], grants=[INVOICE])
        grouped = User.objects.create_user(username="grouped")
        group = Group.objects.create(name="Invoicers")
        group.permissions.set(permissions_for([INVOICE]))
        grouped.groups.add(group)
        User.objects.create_user(username="nobody")
        assert list(users_with_perm(INVOICE)) == [admin_user, grouped, member]
        assert list(users_with_perm(INVOICE, include_superusers=False)) == [
            grouped,
            member,
        ]


@pytest.mark.django_db
class TestPresets:
    def test_every_label_is_a_permission(self):
        for name, preset in PRESETS.items():
            labels = set(preset.members) | set(preset.leads)
            found = {label_of(p) for p in permissions_for(labels)}
            assert found == labels, (name, labels - found)
        assert not permissions_for([]).exists()

    def test_organizers_and_the_migration_agree(self):
        preset = PRESETS[ORGANIZERS]
        assert set(preset.members) == set(migration.ORGANIZER_MEMBER_LABELS)
        assert set(preset.leads) == set(migration.ORGANIZER_LEAD_LABELS)
        assert set(migration.CATALOGUE) == set(preset.members) | set(preset.leads)


@pytest.mark.django_db
class TestOrganizersTeamSeed:
    def test_staff_accounts_join_and_superusers_lead(self, conference, admin_user):
        staff = User.objects.create_user(username="staff", is_staff=True)
        pending = User.objects.create_user(username="late", is_staff=True)
        VolunteerProfile.objects.create(
            user=pending,
            conference=conference,
            application_status=ApplicationStatus.PENDING,
        )
        User.objects.create_user(username="former", is_staff=True, is_active=False)
        User.objects.create_user(username="plain")

        migration.seed_organizers_team(apps, None)
        migration.seed_organizers_team(apps, None)

        team = Team.objects.get(conference=conference, short_name=ORGANIZERS)
        assert not team.open_to_new_members
        assert {label_of(p) for p in team.permissions.all()} == set(
            PRESETS[ORGANIZERS].members
        )
        assert {label_of(p) for p in team.lead_permissions.all()} == set(
            PRESETS[ORGANIZERS].leads
        )
        members = {p.user.username for p in team.approved_members}
        assert members == {"staff", "late", "adminuser"}
        assert {p.user.username for p in team.team_leads.all()} == {"adminuser"}
        assert Team.objects.filter(short_name=ORGANIZERS).count() == 1
        # And the point of it: a staff account holds the organizer set.
        assert fresh(staff).has_perm("speakers.manage_program")
        assert not fresh(staff).has_perm("portal.start_next_year")
        assert fresh(admin_user).has_perm("portal.start_next_year")

    def test_nothing_without_an_active_edition(self, conference):
        Conference.objects.update(is_active=False)
        migration.seed_organizers_team(apps, None)
        assert not Team.objects.filter(short_name=ORGANIZERS).exists()


@pytest.mark.django_db
class TestRolesToOrganizers:
    """The volunteer roles are no longer read: their Admin and Staff
    holders join their edition's Organizers team instead, last year's too,
    and a Vendor or Volunteer role maps to nothing."""

    def test_admin_and_staff_holders_join_their_editions_team(self, conference):
        from volunteer.models import Role

        migration.seed_organizers_team(apps, None)
        past = Conference.objects.create(year=2024, name="Past", slug="past")
        admin_role = Role.objects.create(short_name="Admin", description="d")
        vendor_role = Role.objects.create(short_name="Vendor", description="d")
        lead = VolunteerProfile.objects.create(
            user=User.objects.create_user(username="lead"), conference=past
        )
        lead.roles.add(admin_role)
        vendor = VolunteerProfile.objects.create(
            user=User.objects.create_user(username="vendor"), conference=past
        )
        vendor.roles.add(vendor_role)

        migration.roles_to_organizers(apps, None)

        team = Team.objects.get(conference=past, short_name=ORGANIZERS)
        assert list(team.members.all()) == [lead]
        # Described like this year's Organizers team.
        assert {label_of(p) for p in team.permissions.all()} == set(
            PRESETS[ORGANIZERS].members
        )
        assert str(admin_role) == "Admin"


@pytest.mark.django_db
def test_the_grant_helper_can_make_a_lead(conference):
    from tests.grants import on_team

    user = on_team(User.objects.create_user(username="lee"), lead=True)
    team = Team.objects.get(short_name=ORGANIZERS)
    assert [p.user for p in team.team_leads.all()] == [user]
    assert fresh(user).has_perm("portal.start_next_year")
