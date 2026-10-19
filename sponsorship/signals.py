from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from common.tasks import enqueue

from .models import SponsorshipProfile, SponsorshipProgressStatus
from .tasks import (
    send_internal_sponsor_onboarding_email_task,
    send_internal_sponsor_progress_update_email_task,
    send_sponsorship_approved_email_task,
)


@receiver(pre_save, sender=SponsorshipProfile)
def remember_progress_status(sender, instance, **kwargs):
    """The status as stored, so saving can tell when it became approved."""
    instance._stored_progress_status = (
        sender.objects.filter(pk=instance.pk)
        .values_list("progress_status", flat=True)
        .first()
        if instance.pk
        else None
    )


@receiver(post_save, sender=SponsorshipProfile)
def sponsorship_profile_signal(sender, instance, created, **kwargs):
    """Send emails when sponsorship profile is created or updated.

    Emails are sent asynchronously using Celery tasks to avoid blocking
    the request/response cycle.

    Do not send emails if the instance was created via import/export. (too noisy).
    """
    if hasattr(instance, "from_import_export"):
        return

    if created:
        # Send onboarding email asynchronously
        enqueue(send_internal_sponsor_onboarding_email_task, instance.id)
    else:
        # Send progress update email asynchronously
        enqueue(send_internal_sponsor_progress_update_email_task, instance.id)
    approved = SponsorshipProgressStatus.APPROVED
    if instance.progress_status == approved and (
        getattr(instance, "_stored_progress_status", None) != approved
    ):
        enqueue(send_sponsorship_approved_email_task, instance.id)
