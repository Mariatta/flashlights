from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.template.loader import render_to_string

from common.send_emails import edition_reply_to, send_email


def send_sponsorship_status_emails(profile):
    user = profile.user

    # Email to sponsor
    sponsor_subject = "Your Sponsorship Profile Has Been Approved"
    sponsor_message = render_to_string(
        "sponsorship/email/sponsor_status_update.txt",
        {"user": user, "profile": profile},
    )
    EmailMessage(
        sponsor_subject,
        sponsor_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        reply_to=edition_reply_to(profile.conference),
    ).send()

    # Email to internal team (hardcoded for now)
    team_subject = f"New Sponsorship Approved: {profile.organization_name}"
    team_message = render_to_string(
        "sponsorship/email/team_status_notification.txt",
        {"user": user, "profile": profile},
    )
    send_mail(
        team_subject,
        team_message,
        settings.DEFAULT_FROM_EMAIL,
        ["team@example.com"],  # Replace with actual team emails later
    )


def send_psf_invoice_request_email(profile):
    """Ask whoever issues invoices to prepare the sponsorship contract.

    Goes to ``ACCOUNTING_EMAIL`` and ``SPONSORSHIP_EMAIL`` (settings, both
    optional) and is skipped when neither is set. Through ``send_email``, so
    it is in the sent-email record like every other email the portal sends.
    """
    recipients = [
        address
        for address in (settings.ACCOUNTING_EMAIL, settings.SPONSORSHIP_EMAIL)
        if address
    ]
    if not recipients:
        return
    subject = (
        f"{settings.BRAND.short_name} sponsorship contract request: "
        f"{profile.organization_name}"
    )

    send_email(
        subject,
        recipients,
        markdown_template="sponsorship/email/psf_invoice_request.md",
        context={"profile": profile},
        conference=profile.conference,
    )
