"""The team permissions UI: pickers and a preset on
the team form, the grants on the team page, and where each of a person's
permissions comes from on their profile page."""

import json
import re

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from volunteer.constants import ApplicationStatus
from volunteer.forms import VolunteerProfileReviewForm
from volunteer.models import Team, VolunteerProfile
from volunteer.permission_presets import (
    CATALOGUE,
    ORGANIZERS,
    PRESETS,
    describe,
    grouped_choices,
    label_of,
    permissions_for,
    plain_label,
)
from volunteer.permissions import permission_sources

INVOICE = "sponsorship.send_invoice"


def labels(permissions):
    return sorted(label_of(p) for p in permissions.all())


def payload(conference, **extra):
    data = {
        "conference": conference.pk,
        "short_name": "Sponsorship",
        "description": "Money",
        "open_to_new_members": "on",
    }
    data.update(extra)
    return data


@pytest.mark.django_db
class TestCatalogue:
    def test_every_preset_label_has_plain_words(self):
        words = {label for group in CATALOGUE.values() for label in group}
        for name, preset in PRESETS.items():
            missing = (set(preset.members) | set(preset.leads)) - words
            assert not missing, (name, missing)
        assert plain_label(INVOICE) == "Send sponsor invoices"
        assert plain_label("auth.add_user") == "auth.add_user"
        assert [group for group, _ in grouped_choices()] == list(CATALOGUE)

    def test_describe_groups_in_catalogue_order_with_other_last(self):
        rows = permissions_for([INVOICE, "portal.add_conference", "auth.add_user"])
        assert describe(rows) == [
            ("Conferences", ["Add editions"]),
            ("Sponsorship", ["Send sponsor invoices"]),
            ("Other", ["auth.add_user"]),
        ]


@pytest.mark.django_db
class TestTeamForm:
    def test_pickers_and_the_presets_are_on_the_page(
        self, client, organizer, conference
    ):
        client.force_login(organizer)
        content = client.get(reverse("team_new")).content.decode()
        assert 'name="permissions"' in content and 'name="lead_permissions"' in content
        assert (
            "Start from preset" in content
            and "Review volunteer applications" in content
        )
        assert '<script id="team-presets"' in content
        for name in PRESETS:
            assert f'value="{name}"' in content

    def test_preset_fills_the_sets_when_nothing_is_ticked(
        self, client, organizer, conference
    ):
        client.force_login(organizer)
        response = client.post(
            reverse("team_new"), payload(conference, preset="Sponsorship")
        )
        assert response.status_code == 302
        team = Team.objects.get(short_name="Sponsorship")
        assert labels(team.permissions) == sorted(PRESETS["Sponsorship"].members)
        assert labels(team.lead_permissions) == []

    def test_ticks_win_over_the_preset(self, client, organizer, conference):
        client.force_login(organizer)
        client.post(
            reverse("team_new"),
            payload(
                conference,
                preset="Sponsorship",
                permissions=[INVOICE],
                lead_permissions=["sponsorship.view_unconfirmed_sponsors"],
            ),
        )
        team = Team.objects.get(short_name="Sponsorship")
        assert labels(team.permissions) == [INVOICE]
        assert labels(team.lead_permissions) == [
            "sponsorship.view_unconfirmed_sponsors"
        ]

    def test_edit_shows_and_replaces_the_sets(self, client, organizer, conference):
        team = Team.objects.create(
            conference=conference, short_name="S", description="d"
        )
        team.permissions.set(permissions_for([INVOICE]))
        client.force_login(organizer)
        url = reverse("team_edit", kwargs={"pk": team.pk})
        form = client.get(url).context["form"]
        assert form.initial["permissions"] == [INVOICE]
        response = client.post(
            url,
            payload(
                conference,
                short_name="S",
                permissions=["sponsorship.add_sponsorshipprofile"],
            ),
        )
        assert response.status_code == 302
        assert labels(team.permissions) == ["sponsorship.add_sponsorshipprofile"]

    def test_a_member_holds_what_the_form_granted(self, client, organizer, conference):
        client.force_login(organizer)
        client.post(reverse("team_new"), payload(conference, preset="Sponsorship"))
        team = Team.objects.get(short_name="Sponsorship")
        sam = User.objects.create_user(username="sam")
        profile = VolunteerProfile.objects.create(
            user=sam,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        profile.teams.add(team)
        assert sam.has_perm(INVOICE)


@pytest.mark.django_db
@pytest.mark.django_db
class TestPersonalRailOffersManagementPages:
    def test_specialists_reach_their_pages_from_the_hub(
        self, client, join_team, organizer, conference
    ):
        from speakers.models import SpeakerSettings

        SpeakerSettings.objects.create(
            conference=conference, speaker_module_enabled=True
        )
        hub = reverse("volunteer:index")
        # Whole anchors: "/teams/" is a prefix of My teams' address too.
        sessions = f'href="{reverse("speakers:session_list")}"'
        volunteers = f'href="{reverse("volunteer:volunteers_list")}"'
        teams = f'href="{reverse("teams")}"'

        pat = join_team(User.objects.create_user(username="pat"), "Program")
        client.force_login(pat)
        content = client.get(hub).content.decode()
        assert "Organizing" in content and sessions in content
        assert volunteers not in content and teams not in content

        val = join_team(
            User.objects.create_user(username="val"), "Volunteer coordination"
        )
        client.force_login(val)
        content = client.get(hub).content.decode()
        assert volunteers in content and teams in content and sessions not in content

        sally = join_team(User.objects.create_user(username="sally"), "Sponsorship")
        client.force_login(sally)
        content = client.get(hub).content.decode()
        assert "Organizing" not in content
        assert reverse("sponsorship:sponsorship_list") in content

        # Organizers have the Organize tab and rail for this; no duplicate group.
        client.force_login(organizer)
        assert "Organizing" not in client.get(hub).content.decode()


@pytest.mark.django_db
class TestOrganizeRailFollowsPermissions:
    def test_each_entry_follows_the_permission_its_page_reads(
        self, client, join_team, organizer, conference
    ):
        from speakers.models import SpeakerSettings

        SpeakerSettings.objects.create(
            conference=conference, speaker_module_enabled=True
        )
        dashboard = reverse("organizer_dashboard")
        volunteers = reverse("volunteer:volunteers_list")
        teams = reverse("teams")
        new_team = reverse("team_new")
        sessions = reverse("speakers:session_list")
        board = reverse("speakers:checklist_board")
        sponsors = reverse("sponsorship:sponsorship_list")

        sally = join_team(User.objects.create_user(username="sally"), "Sponsorship")
        client.force_login(sally)
        content = client.get(sponsors).content.decode()
        assert reverse("sponsorship:tier_list") in content
        for url in (dashboard, volunteers, teams, new_team, sessions, board):
            assert url not in content, url

        pat = join_team(User.objects.create_user(username="pat"), "Program")
        client.force_login(pat)
        content = client.get(sessions).content.decode()
        assert board in content and reverse("speakers:presenter_list") in content
        for url in (dashboard, volunteers, teams, new_team, sponsors):
            assert url not in content, url

        client.force_login(organizer)
        content = client.get(dashboard).content.decode()
        for url in (volunteers, teams, new_team, sessions, board, sponsors):
            assert url in content, url


@pytest.mark.django_db
class TestTeamPage:
    def test_lists_what_the_team_may_do(self, client, organizer, conference):
        team = Team.objects.create(
            conference=conference, short_name="S", description="d"
        )
        team.permissions.set(permissions_for(PRESETS["Program"].members))
        team.lead_permissions.set(permissions_for(PRESETS["Program"].leads))
        client.force_login(organizer)
        content = client.get(
            reverse("team_detail", kwargs={"pk": team.pk})
        ).content.decode()
        assert "What this team may do" in content
        assert "Manage the program" in content and "Leads also:" in content
        assert "Change the speaker settings" in content
        # Team and lead permissions are one bullet each, not comma-joined.
        assert re.search(r"<li>\s*Manage the program[^<,]*</li>", content)
        assert re.search(r"<li>\s*Change the speaker settings, [^<]*</li>", content)
        empty = Team.objects.create(
            conference=conference, short_name="Web", description="d"
        )
        content = client.get(
            reverse("team_detail", kwargs={"pk": empty.pk})
        ).content.decode()
        assert "Nothing beyond what every approved volunteer may do" in content


@pytest.mark.django_db
class TestProfilePage:
    def test_where_each_grant_comes_from(
        self, client, conference, join_team, admin_user
    ):
        sam = User.objects.create_user(username="sam", email="sam@x.org")
        join_team(sam, "Sponsorship")
        join_team(sam, "Program", lead=True)
        group = Group.objects.create(name="Infra maintainers")
        group.permissions.set(permissions_for(["portal.add_conference"]))
        sam.groups.add(group)
        profile = VolunteerProfile.objects.get(user=sam)
        sources = permission_sources(profile)
        assert [source for source, _ in sources] == [
            "Group: Infra maintainers",
            f"Approved volunteer, {conference.year}",
            "Team: Program",
            "Lead of Program",
            "Team: Sponsorship",
        ]
        assert sources[1][1] == [("Sponsorship", ["See sponsors"])]
        assert sources[3][1] == [
            (
                "Speakers",
                ["Change the speaker settings, types, roles and readiness gates"],
            ),
            ("Recordings", ["Delete session files"]),
        ]
        # The owner sees it on their own page, and so does a reviewer.
        client.force_login(sam)
        url = reverse("volunteer:volunteer_profile_detail", kwargs={"pk": profile.pk})
        content = client.get(url).content.decode()
        assert "May do:" in content and "Lead of Program" in content
        # One bullet per permission, not a comma-joined line.
        assert re.search(
            r"<li>\s*Change the speaker settings, types, roles and readiness gates\s*</li>",
            content,
        )
        client.force_login(admin_user)
        assert "Lead of Program" in client.get(url).content.decode()
        # A superuser's own page says so, and a past edition grants nothing.
        assert (
            permission_sources(
                VolunteerProfile.objects.create(user=admin_user, conference=conference)
            )[0][0]
            == "Superuser"
        )

    def test_past_edition_and_pending_grant_nothing(self, conference, join_team):
        from portal.models import Conference

        sam = User.objects.create_user(username="sam")
        join_team(sam, "Sponsorship")
        profile = VolunteerProfile.objects.get(user=sam)
        Conference.objects.create(year=2027, name="2027", slug="2027", is_active=True)
        assert permission_sources(profile) == []
        pen = User.objects.create_user(username="pen")
        pending = VolunteerProfile.objects.create(user=pen, conference=conference)
        assert permission_sources(pending) == []
        Conference.objects.update(is_active=False)
        assert permission_sources(profile) == []

    def test_hidden_from_other_volunteers(self, client, conference):
        sam = User.objects.create_user(username="sam")
        profile = VolunteerProfile.objects.create(
            user=sam,
            conference=conference,
            application_status=ApplicationStatus.APPROVED,
        )
        other = User.objects.create_user(username="other")
        client.force_login(other)
        url = reverse("volunteer:volunteer_profile_detail", kwargs={"pk": profile.pk})
        assert client.get(url).status_code == 302

    def test_presets_json_covers_every_preset(self, client, organizer):
        client.force_login(organizer)
        content = client.get(reverse("team_new")).content.decode()
        start = content.index('<script id="team-presets"')
        begin = content.index(">", start) + 1
        end = content.index("</script>", start)
        blob = content[begin:end]
        assert set(json.loads(blob)) == set(PRESETS)


@pytest.fixture
def coordinator(django_user_model, join_team):
    """Edits teams and reviews volunteers, but is not on Organizers."""
    return join_team(
        django_user_model.objects.create_user(
            username="coord", email="coord@example.com"
        ),
        "Volunteer coordination",
    )


@pytest.mark.django_db
class TestOnlyOrganizersGrant:
    def test_a_coordinator_cannot_grant_through_their_own_team(
        self, client, coordinator, conference
    ):
        team = Team.objects.get(short_name="Volunteer coordination")
        before = labels(team.permissions)
        client.force_login(coordinator)
        url = reverse("team_edit", kwargs={"pk": team.pk})
        page = client.get(url).content.decode()
        assert "Only the Organizers team changes what a team may do." in page
        assert 'id="id_preset"' not in page
        response = client.post(
            url,
            payload(
                conference,
                short_name="Volunteer coordination",
                permissions=before + ["portal.start_next_year"],
                lead_permissions=["ticketing.change_ticketingsettings"],
            ),
        )
        assert response.status_code == 302
        assert labels(team.permissions) == before
        assert labels(team.lead_permissions) == []
        coordinator = User.objects.get(pk=coordinator.pk)
        assert not coordinator.has_perm("portal.start_next_year")

    def test_a_coordinators_new_team_grants_nothing(
        self, client, coordinator, conference
    ):
        client.force_login(coordinator)
        client.post(
            reverse("team_new"),
            payload(conference, preset="Sponsorship", permissions=[INVOICE]),
        )
        team = Team.objects.get(short_name="Sponsorship")
        assert labels(team.permissions) == [] and labels(team.lead_permissions) == []

    def test_a_coordinator_cannot_lead_organizers(
        self, client, coordinator, organizer, conference
    ):
        organizers = Team.objects.get(short_name=ORGANIZERS)
        mine = VolunteerProfile.objects.get(user=coordinator)
        client.force_login(coordinator)
        client.post(
            reverse("team_edit", kwargs={"pk": organizers.pk}),
            payload(conference, short_name=ORGANIZERS, team_leads=[mine.pk]),
        )
        assert not organizers.team_leads.filter(pk=mine.pk).exists()

    def test_an_organizer_still_grants(self, client, organizer, conference):
        team = Team.objects.create(conference=conference, short_name="S")
        client.force_login(organizer)
        client.post(
            reverse("team_edit", kwargs={"pk": team.pk}),
            payload(conference, short_name="S", permissions=[INVOICE]),
        )
        assert labels(team.permissions) == [INVOICE]


@pytest.mark.django_db
class TestReviewingApplications:
    def test_nobody_reviews_their_own_application(
        self, client, coordinator, conference
    ):
        """A reviewer cannot move themselves onto another team."""
        program = Team.objects.create(conference=conference, short_name="Program")
        program.permissions.set(permissions_for(PRESETS["Program"].members))
        mine = VolunteerProfile.objects.get(user=coordinator)
        before = list(mine.teams.values_list("pk", flat=True))
        client.force_login(coordinator)
        response = client.post(
            reverse("volunteer:volunteer_profile_manage", kwargs={"pk": mine.pk}),
            {"teams": before + [program.pk]},
        )
        assert response.status_code == 200
        assert "You cannot review your own application" in response.content.decode()
        assert list(mine.teams.values_list("pk", flat=True)) == before

    def test_only_organizers_bring_someone_onto_organizers(
        self, coordinator, organizer, django_user_model, conference
    ):
        applicant = VolunteerProfile.objects.create(
            user=django_user_model.objects.create_user(username="new"),
            conference=conference,
        )
        offered = (
            VolunteerProfileReviewForm(instance=applicant, user=coordinator)
            .fields["teams"]
            .queryset
        )
        assert not offered.filter(short_name=ORGANIZERS).exists()
        offered = (
            VolunteerProfileReviewForm(instance=applicant, user=organizer)
            .fields["teams"]
            .queryset
        )
        assert offered.filter(short_name=ORGANIZERS).exists()
