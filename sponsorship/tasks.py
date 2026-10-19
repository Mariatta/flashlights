from celery import shared_task
from django.conf import settings

from common.send_emails import send_email

from .emails import send_sponsorship_approved_email
from .models import SponsorshipProfile
from .permissions import sponsorship_notification_recipients


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_internal_email_task(self, subject, markdown_template, context):
    """
    Send internal notification emails to team members: everyone holding
    sponsorship.receive_sponsorship_notifications, one email each for
    privacy.
    """
    recipients = sponsorship_notification_recipients()

    if not recipients.exists():
        return f"No recipients found for: {subject}"

    sent_count = 0
    # Send each email individually to each recipient, for privacy reasons
    for recipient in recipients:
        context["recipient_name"] = recipient.get_full_name() or recipient.username

        send_email(
            subject,
            [recipient.email],
            markdown_template=markdown_template,
            context=context,
            user=recipient,
        )
        sent_count += 1

    return f"Sent {sent_count} internal emails: {subject}"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_internal_sponsor_onboarding_email_task(self, profile_id):
    """
    Send onboarding notification to internal team when new sponsor is created.
    """

    try:
        profile = SponsorshipProfile.objects.get(id=profile_id)

        context = {"profile": profile}
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}New Sponsorship Tracking: {profile.organization_name}"
        markdown_template = "emails/sponsorship/internal_sponsor_onboarding.md"

        return send_internal_email_task(subject, markdown_template, context)

    except SponsorshipProfile.DoesNotExist:
        return f"SponsorshipProfile with id {profile_id} not found"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_internal_sponsor_progress_update_email_task(self, profile_id):
    """
    Send progress update notification to internal team.
    """

    try:
        profile = SponsorshipProfile.objects.get(id=profile_id)

        context = {"profile": profile}
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX}Update in Sponsorship Tracking for {profile.organization_name}"
        markdown_template = "emails/sponsorship/internal_sponsor_updated.md"

        return send_internal_email_task(subject, markdown_template, context)

    except SponsorshipProfile.DoesNotExist:
        return f"SponsorshipProfile with id {profile_id} not found"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_sponsorship_approved_email_task(self, profile_id):
    """The approval notice to the edition's address."""
    profile = SponsorshipProfile.objects.filter(id=profile_id).first()
    if profile is None:
        return f"SponsorshipProfile with id {profile_id} not found"
    if send_sponsorship_approved_email(profile):
        return f"Sent the approval notice for {profile.organization_name}"
    return f"No address on {profile.conference} for the approval notice"
