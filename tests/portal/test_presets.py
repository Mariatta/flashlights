"""Demo presets (``manage.py load_preset``; the switcher script has its own
tests in ``tests/test_preset_script.py``) and the migration that drops
untouched backfilled PyLadiesCon editions."""

import importlib
from io import StringIO
from pathlib import Path

import pytest
from allauth.account.models import EmailAddress
from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.db import connection

from portal.celery import app
from portal.models import Conference
from volunteer.models import Team

BARE = Path(__file__).resolve().parents[2] / "presets" / "bare"
EMPTY = BARE.parent / "empty"
drop = importlib.import_module(
    "portal.migrations.0008_flashlights_rebrand"
).drop_untouched


@pytest.mark.django_db
class TestLoadPreset:
    def test_refuses_outside_debug(self, settings):
        settings.DEBUG = False
        with pytest.raises(CommandError, match="DEBUG"):
            call_command("load_preset", str(BARE))

    def test_needs_a_seed_with_run(self, settings, tmp_path):
        settings.DEBUG = True
        with pytest.raises(CommandError, match="No seed.py"):
            call_command("load_preset", str(tmp_path))
        (tmp_path / "seed.py").write_text("VALUE = 1\n")
        with pytest.raises(CommandError, match="defines no run"):
            call_command("load_preset", str(tmp_path))

    def test_loads_the_bare_preset(self, settings):
        settings.DEBUG = True
        Conference.objects.all().delete()
        eager = app.conf.task_always_eager
        out = StringIO()
        call_command("load_preset", str(BARE), stdout=out)
        assert Conference.get_active().name.startswith("Event ")
        assert User.objects.get(username="admin").check_password("password123")
        assert "Loaded the preset" in out.getvalue()
        assert app.conf.task_always_eager == eager  # put back afterwards
        # Preset accounts sign in without the verification email.
        assert EmailAddress.objects.get(user__username="admin").verified

    def test_loads_the_empty_preset(self, settings):
        settings.DEBUG = True
        Conference.objects.all().delete()
        call_command("load_preset", str(EMPTY), stdout=StringIO())
        assert not Conference.objects.exists()
        admin = User.objects.get(username="admin")
        assert admin.is_superuser and admin.check_password("password123")
        # The agreements are left for the first sign-in.
        assert not hasattr(admin, "portalprofile")

    def test_verifies_every_address_once(self, settings, tmp_path):
        """New addresses are added verified, unverified ones are marked,
        verified ones are left alone, and users with no email are skipped."""
        settings.DEBUG = True
        (tmp_path / "seed.py").write_text(
            "from allauth.account.models import EmailAddress\n"
            "from django.contrib.auth.models import User\n"
            "def run(stdout):\n"
            "    User.objects.create_user('new', 'new@example.org')\n"
            "    old = User.objects.create_user('old', 'old@example.org')\n"
            "    EmailAddress.objects.create(user=old, email=old.email)\n"
            "    done = User.objects.create_user('done', 'done@example.org')\n"
            "    EmailAddress.objects.create(\n"
            "        user=done, email=done.email, verified=True, primary=True\n"
            "    )\n"
            "    User.objects.create_user('nobody')\n"
        )
        out = StringIO()
        call_command("load_preset", str(tmp_path), stdout=out)
        assert "Verified 2 email address(es)." in out.getvalue()
        assert not EmailAddress.objects.filter(verified=False).exists()
        assert EmailAddress.objects.count() == 3


@pytest.mark.django_db
class TestDropBackfilledEditions:
    def test_drops_only_untouched_pyladiescon_rows(self):
        Conference.objects.all().delete()
        untouched = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        used = Conference.objects.create(
            year=2025, name="PyLadiesCon 2025", slug="2025"
        )
        Team.objects.create(conference=used, short_name="T", description="d")
        renamed = Conference.objects.create(year=2026, name="Ours 2026", slug="2026")
        with connection.schema_editor(atomic=False) as editor:
            drop(apps, editor)
        remaining = set(Conference.objects.values_list("pk", flat=True))
        assert untouched.pk not in remaining
        assert {used.pk, renamed.pk} <= remaining
