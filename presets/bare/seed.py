"""The bare preset: a fresh instance with one empty edition, this year's,
and one organizer account. What a community sees on day one."""

from django.contrib.auth.models import User
from django.utils import timezone

from portal.models import Conference
from portal_account.models import PortalProfile

PASSWORD = "password123"


def run(stdout):
    year = timezone.now().year
    Conference.objects.update_or_create(
        year=year,
        defaults={"name": f"Event {year}", "slug": str(year), "is_active": True},
    )
    admin, _ = User.objects.get_or_create(
        username="admin",
        defaults={"email": "admin@example.org", "is_staff": True, "is_superuser": True},
    )
    admin.set_password(PASSWORD)
    admin.save()
    PortalProfile.objects.get_or_create(
        user=admin, defaults={"coc_agreement": True, "tos_agreement": True}
    )
    stdout.write(f"Sign in as admin / {PASSWORD}")
