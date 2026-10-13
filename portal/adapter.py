"""django-allauth adapter hooks for the portal."""

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings

from common.send_emails import edition_reply_to


class PortalAccountAdapter(DefaultAccountAdapter):
    """Add portal-wide values to the context of every account email.

    ``unverified_account_retention_days`` lets the verification email tell the
    recipient how long an unverified account survives before it is deleted, so
    the number in the email and the number the cleanup job uses can never
    disagree.
    """

    def send_mail(self, template_prefix, email, context):
        days = settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS
        context = {"unverified_account_retention_days": days, **context}
        super().send_mail(template_prefix, email, context)

    def render_mail(self, template_prefix, email, context, headers=None):
        """Account email replies where the rest of the portal's email does:
        the active edition's reply-to address, when it has one."""
        msg = super().render_mail(template_prefix, email, context, headers=headers)
        reply_to = edition_reply_to()
        if reply_to:
            msg.reply_to = reply_to
        return msg
