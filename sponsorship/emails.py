from django.conf import settings

from common.send_emails import send_email


def send_contract_request_email(profile):
    """Ask whoever issues the community's invoices to prepare the contract.

    Goes to ``ACCOUNTING_EMAIL`` and ``SPONSORSHIP_EMAIL`` (settings, both
    optional) and is skipped when neither is set. Through ``send_email``, so
    it is in the sent-email record like every other email the portal sends,
    and replies go to the edition's address.
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
        markdown_template="sponsorship/email/contract_request.md",
        context={"profile": profile},
        conference=profile.conference,
    )
