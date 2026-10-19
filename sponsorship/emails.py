from django.conf import settings

from common.send_emails import send_email


def send_contract_request_email(profile):
    """Ask whoever issues the community's invoices to prepare the contract.

    Goes to ``ACCOUNTING_EMAIL`` and ``SPONSORSHIP_EMAIL`` (settings, both
    optional) and is skipped when neither is set. Through ``send_email``, so
    it is in the sent-email record like every other email the portal sends,
    and replies go to the edition's address. Returns whether it was sent.
    """
    recipients = [
        address
        for address in (settings.ACCOUNTING_EMAIL, settings.SPONSORSHIP_EMAIL)
        if address
    ]
    if not recipients:
        return False
    subject = (
        f"{settings.BRAND.short_name} sponsorship contract request: "
        f"{profile.organization_name}"
    )

    send_email(
        subject,
        recipients,
        markdown_template="sponsorship/email/contract_request.md",
        context={"profile": profile},
        conference=profile.conference,
    )
    return True


def send_sponsorship_approved_email(profile):
    """Tell the team a sponsorship was approved, at the edition's own address
    (its reply-to, the team's inbox or list). Skipped when the edition has
    none. Returns whether it was sent."""
    address = profile.conference.reply_to_email
    if not address:
        return False
    send_email(
        f"{settings.BRAND.short_name} sponsorship approved: "
        f"{profile.organization_name}",
        [address],
        markdown_template="sponsorship/email/approved.md",
        context={"profile": profile},
        conference=profile.conference,
    )
    return True
