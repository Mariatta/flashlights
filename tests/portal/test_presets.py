"""Demo presets (``manage.py load_preset``, ``scripts/preset.py``) and the
migration that drops untouched backfilled PyLadiesCon editions."""

import importlib
from io import StringIO
from pathlib import Path

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from portal.celery import app
from portal.models import Conference
from volunteer.models import Team

BARE = Path(__file__).resolve().parents[2] / "presets" / "bare"
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
        drop(apps, None)
        remaining = set(Conference.objects.values_list("pk", flat=True))
        assert untouched.pk not in remaining
        assert {used.pk, renamed.pk} <= remaining
