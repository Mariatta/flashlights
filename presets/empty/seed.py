"""The empty preset: one superuser and nothing else, not even an edition,
so setting up an instance can be walked through from the first screen."""

from django.contrib.auth.models import User

PASSWORD = "password123"


def run(stdout):
    admin, _ = User.objects.get_or_create(
        username="admin",
        defaults={"email": "admin@example.org", "is_staff": True, "is_superuser": True},
    )
    admin.set_password(PASSWORD)
    admin.save()
    stdout.write(f"Sign in as admin / {PASSWORD}")
