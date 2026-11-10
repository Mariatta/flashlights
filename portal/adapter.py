"""django-allauth adapter hooks for the portal."""

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings

from common.send_emails import edition_reply_to
from portal.models import Conference


class PortalAccountAdapter(DefaultAccountAdapter):
    """Add portal-wide values to the context of every account email.

    ``unverified_account_retention_days`` lets the verification email tell the
    recipient how long an unverified account survives before it is deleted, so
    the number in the email and the number the cleanup job uses can never
    disagree.
    """

    def send_mail(self, template_prefix, email, context):
        days = settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS
        # The instance's name for the footer, as every other email signs.
        context = {
            "unverified_account_retention_days": days,
            "brand": settings.BRAND,
            # The active edition, for the sign-off's link to its website.
            "active_conference": Conference.get_active(),
            **context,
        }
        super().send_mail(template_prefix, email, context)

    def render_mail(self, template_prefix, email, context, headers=None):
        """Account email replies where the rest of the portal's email does:
        the active edition's reply-to address, when it has one."""
        msg = super().render_mail(template_prefix, email, context, headers=headers)
        # send_mail put the active edition in the context: reuse it.
        reply_to = edition_reply_to(context.get("active_conference"))
        if reply_to:
            msg.reply_to = reply_to
        return msg
