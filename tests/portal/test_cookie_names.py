"""The session and CSRF cookies carry their own names, overridable by env var."""

import runpy
from pathlib import Path

import pytest
from django.conf import settings

SETTINGS = Path(settings.BASE_DIR) / "portal" / "settings.py"


def test_defaults():
    assert settings.SESSION_COOKIE_NAME == "flashlights_sessionid"
    assert settings.CSRF_COOKIE_NAME == "flashlights_csrftoken"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_NAME", "summit_sessionid")
    monkeypatch.setenv("CSRF_COOKIE_NAME", "summit_csrftoken")
    loaded = runpy.run_path(str(SETTINGS))
    assert loaded["SESSION_COOKIE_NAME"] == "summit_sessionid"
    assert loaded["CSRF_COOKIE_NAME"] == "summit_csrftoken"


@pytest.mark.django_db
def test_login_sets_the_named_cookie(client, django_user_model):
    user = django_user_model.objects.create_user("ada", password="pw")
    client.force_login(user)
    assert "flashlights_sessionid" in client.cookies
    assert "sessionid" not in client.cookies
