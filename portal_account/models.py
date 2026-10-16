from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse

from portal.models import BaseModel

from .handles import CHANNEL_CHOICES


class PortalProfile(BaseModel):

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    pronouns = models.CharField(max_length=100, blank=True, null=True)
    coc_agreement = models.BooleanField(default=False)
    tos_agreement = models.BooleanField(default=False)
    profile_picture = models.ImageField(
        upload_to="profile_pictures", blank=True, null=True
    )

    class Meta:
        permissions = [
            ("view_maintenance", "Can view the maintenance section"),
        ]

    def get_absolute_url(self):
        return reverse("portal_account:portal_profile_edit", kwargs={"pk": self.pk})

    def __str__(self):
        return self.user.username


class Handle(models.Model):
    """One of a person's handles (GitHub, Discord, Mastodon, ...): the
    record every form that asks reads and writes. The volunteer and
    presenter rows carry copies of it; see ``portal_account.handles``.
    A plain model with its own timestamps: ``BaseModel`` is concrete."""

    creation_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="handles")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    value = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "channel"], name="portal_account_handle_per_channel"
            )
        ]
        ordering = ["user_id", "channel"]

    def __str__(self):
        return f"{self.user.username}: {self.get_channel_display()} {self.value}"
