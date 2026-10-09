import pytest
from django.contrib.auth.models import User
from django.core import mail

from common.models import SentEmail
from sponsorship.emails import (
    send_psf_invoice_request_email,
    send_sponsorship_status_emails,
)
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)


@pytest.mark.django_db
class TestSponsorshipEmails:
    def test_send_sponsorship_status_emails(self, conference):
        """Test that sponsorship status emails are sent correctly."""
        user = User.objects.create_user(
            username="sponsor", email="sponsor@example.com", password="testpass"
        )

        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            user=user,
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )

        # Clear the mail outbox
        mail.outbox = []

        # Send the emails
        send_sponsorship_status_emails(profile)

        # Check that two emails were sent (one to sponsor, one to team)
        assert len(mail.outbox) == 2

        # Check sponsor email
        sponsor_email = mail.outbox[0]
        assert "Your Sponsorship Profile Has Been Approved" in sponsor_email.subject
        assert sponsor_email.to == ["sponsor@example.com"]

        # Check team email
        team_email = mail.outbox[1]
        assert "New Sponsorship Approved: Test Corp" in team_email.subject
        assert team_email.to == ["team@example.com"]

    def test_send_psf_invoice_request_email(self, conference, settings):
        """The contract request goes to both configured addresses."""
        settings.ACCOUNTING_EMAIL = "accounting@example.org"
        settings.SPONSORSHIP_EMAIL = "sponsors@example.org"
        tier = SponsorshipTier.objects.create(
            name="Gold",
            amount=5000.00,
            description="Gold tier sponsorship",
            conference=conference,
        )

        profile = SponsorshipProfile.objects.create(
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            sponsors_contact_email="contact@testcorp.com",
            conference=conference,
        )

        # Clear the mail outbox
        mail.outbox = []

        # Send the email
        send_psf_invoice_request_email(profile)

        # Check that one email was sent, and recorded like every other
        assert len(mail.outbox) == 1
        record = SentEmail.objects.get()
        assert record.conference == conference
        assert record.context_digest == {"profile": profile.pk}
        assert "Test Corp" in record.body_md

        email = mail.outbox[0]

        # Check email subject
        assert "Flashlights sponsorship contract request: Test Corp" in email.subject

        # Check recipients
        assert "accounting@example.org" in email.to
        # Ensure the project recipients include our sponsors contact
        assert "sponsors@example.org" in email.to

        # Check email body contains expected content
        assert "Test Corp" in email.body
        assert "Gold" in email.body
        assert "$5000" in email.body  # Amount formatting may vary

    def test_invoice_request_skipped_without_recipients(self, conference, settings):
        """An instance with no accounting or sponsorship address configured
        sends nothing rather than an email to nobody."""
        settings.ACCOUNTING_EMAIL = ""
        settings.SPONSORSHIP_EMAIL = ""
        tier = SponsorshipTier.objects.create(
            name="Gold", amount=5000.00, description="Gold", conference=conference
        )
        profile = SponsorshipProfile.objects.create(
            organization_name="Test Corp",
            sponsorship_tier=tier,
            progress_status=SponsorshipProgressStatus.APPROVED,
            conference=conference,
        )
        mail.outbox = []
        send_psf_invoice_request_email(profile)
        assert mail.outbox == []
        assert not SentEmail.objects.exists()
