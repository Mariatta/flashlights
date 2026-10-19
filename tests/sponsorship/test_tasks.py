import pytest
from django.contrib.auth.models import User
from django.core import mail

from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from sponsorship.tasks import (
    send_internal_email_task,
    send_internal_sponsor_onboarding_email_task,
    send_internal_sponsor_progress_update_email_task,
    send_sponsorship_approved_email_task,
)
from volunteer.models import Region, VolunteerProfile


@pytest.fixture
def admin_user_with_role(conference):
    """Create an admin user with proper role."""
    admin_user = User.objects.create_superuser(
        username="testadmin",
        email="test-admin@example.com",
        password="admin-test-password",
    )
    admin_profile = VolunteerProfile(user=admin_user, conference=conference)
    admin_profile.region = Region.NORTH_AMERICA
    admin_profile.save()
    return admin_user


@pytest.fixture
def sponsorship_profile(admin_user, conference):
    """Create a test sponsorship profile."""
    return SponsorshipProfile.objects.create(
        main_contact_user=admin_user,
        organization_name="Test Org",
        progress_status=SponsorshipProgressStatus.AWAITING_RESPONSE.value,
        conference=conference,
    )


@pytest.mark.django_db
class TestSponsorshipTasks:
    """Test cases for sponsorship Celery tasks."""

    def test_send_internal_email_task(self, admin_user_with_role):
        """Test internal email task sends to admin users."""
        mail.outbox.clear()

        result = send_internal_email_task(
            subject="Test Subject",
            markdown_template="emails/sponsorship/internal_sponsor_onboarding.md",
            context={"profile": {"organization_name": "Test Org"}},
        )

        assert "Sent" in result
        assert len(mail.outbox) >= 1
        assert mail.outbox[0].subject == "Test Subject"

    def test_send_internal_email_task_no_recipients(self):
        """Test internal email task when no recipients exist."""
        mail.outbox.clear()

        result = send_internal_email_task(
            subject="Test Subject",
            markdown_template="emails/sponsorship/internal_sponsor_onboarding.md",
            context={"profile": {"organization_name": "Test Org"}},
        )

        assert "No recipients found" in result
        assert len(mail.outbox) == 0

    def test_send_internal_sponsor_onboarding_email_task(
        self, admin_user_with_role, sponsorship_profile
    ):
        """Test onboarding email task is sent."""
        mail.outbox.clear()

        result = send_internal_sponsor_onboarding_email_task(sponsorship_profile.id)

        assert "Sent" in result
        assert len(mail.outbox) >= 1

    def test_send_internal_sponsor_onboarding_email_task_profile_not_found(self):
        """Test onboarding email task when profile doesn't exist."""
        result = send_internal_sponsor_onboarding_email_task(99999)
        assert "SponsorshipProfile with id 99999 not found" in result

    def test_send_internal_sponsor_progress_update_email_task(
        self, admin_user_with_role, sponsorship_profile
    ):
        """Test progress update email task is sent."""
        mail.outbox.clear()

        result = send_internal_sponsor_progress_update_email_task(
            sponsorship_profile.id
        )

        assert "Sent" in result
        assert len(mail.outbox) >= 1

    def test_send_internal_sponsor_progress_update_email_task_profile_not_found(self):
        """Test progress update email task when profile doesn't exist."""
        result = send_internal_sponsor_progress_update_email_task(99999)
        assert "SponsorshipProfile with id 99999 not found" in result


@pytest.mark.django_db
class TestApprovalNotice:
    """When a sponsorship becomes approved, the team hears at the edition's
    own address."""

    def approval_notices(self):
        return [m for m in mail.outbox if "sponsorship approved" in m.subject]

    def test_sent_once_when_the_status_becomes_approved(
        self, sponsorship_profile, conference
    ):
        conference.reply_to_email = "team@example.org"
        conference.save()
        mail.outbox.clear()
        sponsorship_profile.progress_status = SponsorshipProgressStatus.APPROVED
        sponsorship_profile.save()
        [notice] = self.approval_notices()
        assert notice.to == ["team@example.org"]
        assert "Test Org" in notice.subject and "is approved" in notice.body
        # Nothing recorded yet for tier or contact: those lines are left out.
        assert "Tier:" not in notice.body and "None" not in notice.body
        # Saved again while approved: no second notice.
        sponsorship_profile.organization_name = "Test Org Inc"
        sponsorship_profile.save()
        assert len(self.approval_notices()) == 1

    def test_a_sponsor_added_as_approved_is_announced(self, admin_user, conference):
        conference.reply_to_email = "team@example.org"
        conference.save()
        mail.outbox.clear()
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000, description="d", conference=conference
        )
        SponsorshipProfile.objects.create(
            main_contact_user=admin_user,
            organization_name="Ready Org",
            sponsorship_tier=tier,
            sponsor_contact_name="Rae",
            sponsors_contact_email="rae@ready.example",
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )
        [notice] = self.approval_notices()
        assert "Tier: Gold" in notice.body
        assert "Contact name: Rae" in notice.body
        assert "Contact email: rae@ready.example" in notice.body

    def test_skipped_without_an_address(self, sponsorship_profile):
        mail.outbox.clear()
        sponsorship_profile.progress_status = SponsorshipProgressStatus.APPROVED
        sponsorship_profile.save()
        assert self.approval_notices() == []
        result = send_sponsorship_approved_email_task(sponsorship_profile.id)
        assert result.startswith("No address on")

    def test_profile_not_found(self):
        assert "not found" in send_sponsorship_approved_email_task(99999)
