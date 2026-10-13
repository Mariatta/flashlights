"""Load a demo preset into the current database: ``manage.py load_preset
<preset directory>`` (DEBUG only, like the other sample-data commands).

A preset is a directory with a ``seed.py`` defining ``run(stdout)``, which
creates the editions, people and data the preset shows, and an optional
``env`` file the switcher (``scripts/preset.py``) reads for the branding.
The bare preset ships in ``presets/``; presets with a real community's
data live outside the repository, wherever ``PRESETS_PATH`` points.
"""

import runpy
from pathlib import Path

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings

from portal.celery import app


class Command(BaseCommand):
    help = "Load a demo preset's data into this database (DEBUG only)."

    def add_arguments(self, parser):
        parser.add_argument("preset", help="The preset's directory.")

    def handle(self, *args, preset, **options):
        if not settings.DEBUG:
            raise CommandError(
                "load_preset only runs in development (DEBUG=True); presets "
                "create accounts with a known password."
            )
        seed = Path(preset).expanduser() / "seed.py"
        if not seed.is_file():
            raise CommandError(f"No seed.py in {preset}.")
        run = runpy.run_path(str(seed)).get("run")
        if not callable(run):
            raise CommandError(f"{seed} defines no run(stdout).")
        # A preset invites and accepts people: run those tasks here and keep
        # their emails in memory, so loading never mails anyone or leaves
        # work queued for a worker on another database.
        eager = app.conf.task_always_eager
        app.conf.task_always_eager = True
        try:
            with override_settings(
                EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
            ), transaction.atomic():
                run(self.stdout)
                verified = verify_everyone()
        finally:
            app.conf.task_always_eager = eager
        self.stdout.write(f"Verified {verified} email address(es).")
        self.stdout.write(self.style.SUCCESS(f"Loaded the preset in {preset}."))


def verify_everyone():
    """Every preset account signs in without the verification email: each
    one's address is recorded as verified and primary. Returns how many
    addresses were added or marked verified."""
    count = 0
    for user in get_user_model().objects.exclude(email=""):
        address, created = EmailAddress.objects.get_or_create(
            user=user,
            email__iexact=user.email,
            defaults={"email": user.email, "verified": True, "primary": True},
        )
        if created:
            count += 1
        elif not address.verified:
            address.verified = True
            address.save(update_fields=["verified"])
            count += 1
    return count
