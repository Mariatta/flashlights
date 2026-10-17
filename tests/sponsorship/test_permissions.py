"""Sponsorship on has_perm (design §7.1): a Sponsorship-team
member manages sponsors with no Django flag, an approved volunteer only
reads, and the internal email reaches the team."""

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from sponsorship.forms import SponsorshipProfileForm
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from sponsorship.tasks import send_internal_email_task
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

LIST = reverse("sponsorship:sponsorship_list")
NEW = reverse("sponsorship:sponsorship_profile_new")
TIERS = reverse("sponsorship:tier_list")


@pytest.fixture
def sponsor(conference):
    return SponsorshipProfile.objects.create(
        organization_name="Paid Corp",
        conference=conference,
        progress_status=SponsorshipProgressStatus.PAID,
    )


@pytest.fixture
def prospect(conference):
    return SponsorshipProfile.objects.create(
        organization_name="Maybe Inc",
        conference=conference,
        progress_status=SponsorshipProgressStatus.NOT_CONTACTED,
    )


@pytest.fixture
def manager(join_team):
    return join_team(
        User.objects.create_user(username="sally", email="sally@x.org"), "Sponsorship"
    )


@pytest.fixture
def reader(conference):
    user = User.objects.create_user(username="vol", email="vol@x.org")
    VolunteerProfile.objects.create(
        user=user, conference=conference, application_status=ApplicationStatus.APPROVED
    )
    return user


def detail(profile):
    return reverse("sponsorship:sponsorship_profile_detail", args=[profile.pk])


@pytest.mark.django_db
class TestSponsorshipTeamMember:
    def test_manages_sponsors_with_no_flag(
        self, client, manager, conference, sponsor, prospect
    ):
        assert not manager.is_staff and not manager.is_superuser
        client.force_login(manager)
        response = client.get(LIST)
        assert response.status_code == 200
        # Every status, the actions column, the attention buckets, the heading.
        names = {p.organization_name for p in response.context["object_list"]}
        assert names == {"Paid Corp", "Maybe Inc"}
        assert "actions" in response.context["table"].columns.names()
        assert "attention_unpaid" in response.context
        content = response.content.decode()
        assert "Add sponsor" in content and NEW in content
        assert client.get(NEW).status_code == 200
        assert client.get(TIERS).status_code == 200
        assert client.get(reverse("sponsorship:tier_new")).status_code == 200
        edit = reverse("sponsorship:sponsorship_profile_edit", args=[sponsor.pk])
        assert client.get(edit).status_code == 200
        page = client.get(detail(sponsor)).content.decode()
        assert edit in page
        assert (
            reverse("sponsorship:sponsorship_profile_delete", args=[sponsor.pk]) in page
        )

    def test_sends_the_invoice_request(self, client, manager, conference, settings):
        settings.ACCOUNTING_EMAIL = "accounts@example.org"
        approved = SponsorshipProfile.objects.create(
            organization_name="Ready Ltd",
            conference=conference,
            progress_status=SponsorshipProgressStatus.APPROVED,
        )
        client.force_login(manager)
        assert client.get(detail(approved)).context["can_send_invoice"] is True
        mail.outbox.clear()
        response = client.post(
            reverse("sponsorship:sponsorship_contract_request", args=[approved.pk])
        )
        assert response.status_code == 302
        assert any("contract request" in m.subject for m in mail.outbox)

    def test_sees_every_edition(self, client, manager, conference):
        from portal.models import Conference

        Conference.objects.create(year=2020, name="2020", slug="2020")
        client.force_login(manager)
        years = {c.year for c in client.get(LIST).context["conferences"]}
        assert years == {conference.year, 2020}

    def test_no_active_edition_shows_the_latest(self, client, admin_user, conference):
        """A manager with no active edition lands on the most recent year."""
        from portal.models import Conference

        older = Conference.objects.create(year=2020, name="2020", slug="2020")
        SponsorshipProfile.objects.create(
            organization_name="Old Corp",
            conference=older,
            progress_status=SponsorshipProgressStatus.PAID,
        )
        Conference.objects.update(is_active=False)
        client.force_login(admin_user)
        response = client.get(LIST)
        assert response.context["selected_conference"] == conference

    def test_is_offered_as_internal_contact(self, manager, admin_user, reader):
        candidates = set(SponsorshipProfileForm().fields["main_contact_user"].queryset)
        assert candidates == {manager, admin_user}


@pytest.mark.django_db
class TestApprovedVolunteer:
    def test_reads_and_nothing_more(
        self, client, reader, conference, sponsor, prospect
    ):
        client.force_login(reader)
        response = client.get(LIST)
        assert response.status_code == 200
        names = {p.organization_name for p in response.context["object_list"]}
        assert names == {"Paid Corp"}, "unconfirmed sponsors stay hidden"
        assert "actions" not in response.context["table"].columns.names()
        assert "attention_unpaid" not in response.context
        content = response.content.decode()
        assert "Add sponsor" not in content and NEW not in content
        page = client.get(detail(sponsor))
        assert page.status_code == 200
        assert page.context["can_send_invoice"] is False
        assert "Edit" not in page.content.decode().split("Sponsorship Information")[0]
        for url in (
            NEW,
            TIERS,
            reverse("sponsorship:sponsorship_profile_edit", args=[sponsor.pk]),
            reverse("sponsorship:sponsorship_profile_delete", args=[sponsor.pk]),
            reverse("sponsorship:sponsorship_contract_request", args=[sponsor.pk]),
        ):
            assert client.get(url).status_code == 403, url
        assert (
            client.post(
                reverse("sponsorship:sponsorship_contract_request", args=[sponsor.pk])
            ).status_code
            == 403
        )

    def test_staff_flag_alone_opens_nothing(self, client, conference, sponsor):
        staff = User.objects.create_user(username="staffy", is_staff=True)
        client.force_login(staff)
        assert client.get(LIST).status_code == 403
        assert client.get(NEW).status_code == 403


@pytest.mark.django_db
class TestNotifications:
    def test_internal_email_reaches_the_team(self, manager, reader, admin_user):
        mail.outbox.clear()
        result = send_internal_email_task(
            subject="New sponsor",
            markdown_template="emails/sponsorship/internal_sponsor_onboarding.md",
            context={"profile": {"organization_name": "Test Org"}},
        )
        assert result == "Sent 2 internal emails: New sponsor"
        assert sorted(m.to[0] for m in mail.outbox) == sorted(
            [manager.email, admin_user.email]
        )

    def test_tiers_are_the_teams_too(self, client, manager, conference):
        tier = SponsorshipTier.objects.create(
            conference=conference, name="Gold", amount=1, description="g"
        )
        client.force_login(manager)
        assert (
            client.get(reverse("sponsorship:tier_edit", args=[tier.pk])).status_code
            == 200
        )
        assert (
            client.get(reverse("sponsorship:tier_delete", args=[tier.pk])).status_code
            == 200
        )
