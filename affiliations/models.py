"""A person's affiliations: free text with a kind, as many as they like.

Flashlights' replacement for the upstream PyLadies chapter, which was one
pick from a list. A meetup member might name a workplace, a project and a
community; a summit speaker a lab and a maintained package. The rows hang
off the user, not the volunteer profile, so a speaker's and a volunteer's
affiliations are the same rows.
"""

from django.conf import settings
from django.db import models


class AffiliationKind(models.TextChoices):
    WORKPLACE = "workplace", "Workplace"
    PROJECT = "project", "Project"
    COMMUNITY = "community", "Community"
    SCHOOL = "school", "School"
    OTHER = "other", "Other"


class Affiliation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="affiliations",
    )
    kind = models.CharField(
        max_length=20,
        choices=AffiliationKind.choices,
        default=AffiliationKind.WORKPLACE,
    )
    name = models.CharField(max_length=120)
    url = models.URLField(blank=True, default="", help_text="Optional link.")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.name}"
