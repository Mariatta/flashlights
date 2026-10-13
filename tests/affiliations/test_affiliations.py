"""Affiliations on the volunteer profile, and the dev seed command."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from affiliations.models import Affiliation, AffiliationKind
from volunteer.constants import Region
from volunteer.models import VolunteerProfile

PROFILE = {
    "timezone": "UTC",
    "github_username": "test-github",
    "discord_username": "testdiscord1234",
    "availability_hours_per_week": 10,
    "region": Region.NORTH_AMERICA,
}


def rows(*entries, existing=()):
    """POST data for the inline formset: existing rows first, then new."""
    data = {
        "affiliations-TOTAL_FORMS": str(len(existing) + len(entries)),
        "affiliations-INITIAL_FORMS": str(len(existing)),
        "affiliations-MIN_NUM_FORMS": "0",
        "affiliations-MAX_NUM_FORMS": "1000",
    }
    index = 0
    for affiliation, delete in existing:
        data[f"affiliations-{index}-id"] = str(affiliation.pk)
        data[f"affiliations-{index}-kind"] = affiliation.kind
        data[f"affiliations-{index}-name"] = affiliation.name
        data[f"affiliations-{index}-url"] = affiliation.url
        if delete:
            data[f"affiliations-{index}-DELETE"] = "on"
        index += 1
    for kind, name, url in entries:
        data[f"affiliations-{index}-kind"] = kind
        data[f"affiliations-{index}-name"] = name
        data[f"affiliations-{index}-url"] = url
        index += 1
    return data


@pytest.mark.django_db
class TestVolunteerProfileAffiliations:
    def test_str(self, portal_user):
        affiliation = Affiliation.objects.create(
            user=portal_user, kind=AffiliationKind.PROJECT, name="httpx"
        )
        assert str(affiliation) == "Project: httpx"

    def test_form_page_renders_rows_and_names(self, client, portal_user, conference):
        Affiliation.objects.create(
            user=portal_user, kind=AffiliationKind.WORKPLACE, name="Acme"
        )
        client.force_login(portal_user)
        content = client.get(
            reverse("volunteer:volunteer_profile_new")
        ).content.decode()
        assert "Affiliations" in content
        assert 'value="Acme"' in content  # the datalist
        assert "affiliations-TOTAL_FORMS" in content
        assert "affiliations/formset." in content  # hashed by the manifest

    def test_create_profile_with_affiliations(self, client, portal_user, conference):
        client.force_login(portal_user)
        data = {
            **PROFILE,
            **rows(
                (AffiliationKind.WORKPLACE, "Acme", "https://acme.example.org"),
                (AffiliationKind.COMMUNITY, "Vancouver Python", ""),
            ),
        }
        response = client.post(reverse("volunteer:volunteer_profile_new"), data=data)
        assert response.status_code == 302
        assert VolunteerProfile.objects.filter(user=portal_user).exists()
        assert [str(a) for a in portal_user.affiliations.all()] == [
            "Workplace: Acme",
            "Community: Vancouver Python",
        ]

    def test_blank_rows_are_ignored(self, client, portal_user, conference):
        client.force_login(portal_user)
        data = {**PROFILE, **rows((AffiliationKind.WORKPLACE, "", ""))}
        response = client.post(reverse("volunteer:volunteer_profile_new"), data=data)
        assert response.status_code == 302
        assert not portal_user.affiliations.exists()

    def test_bad_row_keeps_the_profile_unsaved(self, client, portal_user, conference):
        client.force_login(portal_user)
        data = {**PROFILE, **rows((AffiliationKind.WORKPLACE, "Acme", "not a url"))}
        response = client.post(reverse("volunteer:volunteer_profile_new"), data=data)
        assert response.status_code == 200
        assert "Enter a valid URL" in response.content.decode()
        assert not VolunteerProfile.objects.filter(user=portal_user).exists()
        assert not portal_user.affiliations.exists()

    def test_edit_removes_and_adds(self, client, portal_user, conference):
        profile = VolunteerProfile.objects.create(
            user=portal_user,
            conference=conference,
            region=Region.ASIA,
            discord_username="x",
            availability_hours_per_week=1,
        )
        old = Affiliation.objects.create(
            user=portal_user, kind=AffiliationKind.SCHOOL, name="Old school"
        )
        client.force_login(portal_user)
        data = {
            **PROFILE,
            **rows(
                (AffiliationKind.PROJECT, "CPython", ""),
                existing=[(old, True)],
            ),
        }
        response = client.post(
            reverse("volunteer:volunteer_profile_edit", kwargs={"pk": profile.pk}),
            data=data,
        )
        assert response.status_code == 302
        assert [str(a) for a in portal_user.affiliations.all()] == ["Project: CPython"]

    def test_detail_and_review_show_affiliations(
        self, client, portal_user, admin_user, conference
    ):
        profile = VolunteerProfile.objects.create(
            user=portal_user,
            conference=conference,
            region=Region.ASIA,
            discord_username="x",
            availability_hours_per_week=1,
        )
        Affiliation.objects.create(
            user=portal_user,
            kind=AffiliationKind.PROJECT,
            name="CPython",
            url="https://python.org",
        )
        client.force_login(admin_user)
        detail = client.get(
            reverse("volunteer:volunteer_profile_detail", kwargs={"pk": profile.pk})
        ).content.decode()
        assert 'href="https://python.org"' in detail and "CPython" in detail
        review = client.get(
            reverse("volunteer:volunteer_profile_manage", kwargs={"pk": profile.pk})
        ).content.decode()
        assert "Affiliations" in review and "CPython" in review

    def test_notification_email_lists_affiliations(
        self, portal_user, conference, mailoutbox
    ):
        Affiliation.objects.create(
            user=portal_user, kind=AffiliationKind.WORKPLACE, name="Acme"
        )
        VolunteerProfile.objects.create(
            user=portal_user,
            conference=conference,
            region=Region.ASIA,
            discord_username="x",
            availability_hours_per_week=1,
        )
        assert "Affiliations: Workplace: Acme" in "".join(m.body for m in mailoutbox)


@pytest.mark.django_db
class TestSeedDevData:
    def test_refuses_outside_debug(self, settings):
        settings.DEBUG = False
        with pytest.raises(CommandError, match="DEBUG"):
            call_command("seed_dev_data", stdout=StringIO())

    def test_seeds_accounts_and_affiliations(self, settings):
        settings.DEBUG = True
        out = StringIO()
        call_command("seed_dev_data", stdout=out)
        call_command("seed_dev_data", stdout=StringIO())  # idempotent
        from django.contrib.auth.models import User

        for username in ("admin_user", "organizer_lena", "volunteer1", "ada"):
            user = User.objects.get(username=username)
            assert user.check_password("password123"), username
        assert Affiliation.objects.filter(user__username="volunteer1").count() == 3
        assert Affiliation.objects.filter(user__username="ada").count() == 2
        assert "ada" in out.getvalue() and "Speaker" in out.getvalue()
        # A past in-person edition next to the online one.
        from portal.models import Conference

        past = Conference.objects.get(year=2024)
        assert past.venue_name.startswith("Vancouver") and not past.uses_discord
        assert past.speaker_settings.event_format == "IN_PERSON"
        assert past.speaker_settings.recordings == "TEAM"
        assert Conference.get_active().year != 2024
