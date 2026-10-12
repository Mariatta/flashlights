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

from django.conf import settings
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
        finally:
            app.conf.task_always_eager = eager
        self.stdout.write(self.style.SUCCESS(f"Loaded the preset in {preset}."))
