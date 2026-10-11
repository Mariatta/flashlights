"""The boot contract: a production start names every missing variable."""

import json
import os
import subprocess
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

from portal import boot

FULL = {
    "SECRET_KEY": "s",
    "DJANGO_ALLOWED_HOSTS": "portal.example.org",
    "DATABASE_URL": "postgresql://x",
    "REDIS_URL": "redis://x",
    "FERNET_KEY": "k",
    "EMAIL_URL": "smtp://u:p@mail.example.org:587/?tls=true",
    "DJANGO_DEFAULT_FROM_EMAIL": "Summit <noreply@example.org>",
    "AWS_ACCESS_KEY_ID": "a",
    "AWS_SECRET_ACCESS_KEY": "b",
    "AWS_STORAGE_BUCKET_NAME": "c",
    "AWS_S3_ENDPOINT_URL": "https://s3.example.org",
}


class TestMissing:
    def test_a_full_production_environment_passes(self):
        assert boot.missing(FULL, production=True) == []
        boot.check(FULL, debug=False)

    def test_development_needs_only_the_secret_key(self):
        assert boot.missing({"SECRET_KEY": "s"}, production=False) == []
        assert [n for n, _ in boot.missing({}, production=False)] == [("SECRET_KEY",)]

    def test_every_gap_is_named_at_once(self):
        env = {
            k: v
            for k, v in FULL.items()
            if k not in ("DATABASE_URL", "REDIS_URL", "AWS_S3_ENDPOINT_URL")
        }
        with pytest.raises(ImproperlyConfigured) as excinfo:
            boot.check(env, debug=False)
        message = str(excinfo.value)
        assert "DATABASE_URL" in message
        assert "CELERY_BROKER_URL or REDIS_URL" in message
        assert "AWS_S3_ENDPOINT_URL" in message
        assert "SECRET_KEY" not in message
        assert message.count("\n  ") == 3

    def test_blank_counts_as_missing_and_alternatives_satisfy(self):
        env = {**FULL, "REDIS_URL": "  ", "CELERY_BROKER_URL": "redis://y"}
        assert boot.missing(env, production=True) == []
        env = {**FULL, "EMAIL_URL": "", "DJANGO_EMAIL_HOST": "mail.example.org"}
        assert boot.missing(env, production=True) == []

    def test_the_check_can_be_switched_off(self):
        boot.check({"BOOT_CHECK": "0"}, debug=False)
        with pytest.raises(ImproperlyConfigured):
            boot.check({"BOOT_CHECK": "1"}, debug=False)


class TestSwitch:
    def test_first_name_set_wins_and_default_applies(self):
        assert boot.switch(
            {"USE_OBJECT_STORAGE": "true"}, "USE_OBJECT_STORAGE", "USE_SPACES"
        )
        assert boot.switch({"USE_SPACES": "true"}, "USE_OBJECT_STORAGE", "USE_SPACES")
        assert not boot.switch(
            {"USE_OBJECT_STORAGE": "0", "USE_SPACES": "true"},
            "USE_OBJECT_STORAGE",
            "USE_SPACES",
        )
        assert not boot.switch({}, "USE_OBJECT_STORAGE", "USE_SPACES")
        assert boot.switch({}, "X", default="true")


class TestEmailUrl:
    def test_starttls_with_credentials(self):
        assert boot.email_url(
            "smtp://user%40x:p%23w@mail.example.org:2525/?tls=true"
        ) == {
            "EMAIL_HOST": "mail.example.org",
            "EMAIL_PORT": 2525,
            "EMAIL_HOST_USER": "user@x",
            "EMAIL_HOST_PASSWORD": "p#w",
            "EMAIL_USE_TLS": True,
            "EMAIL_USE_SSL": False,
        }

    def test_default_ports(self):
        assert boot.email_url("smtp://mail.example.org")["EMAIL_PORT"] == 25
        assert boot.email_url("smtp://mail.example.org/?tls=1")["EMAIL_PORT"] == 587
        ssl = boot.email_url("smtps://mail.example.org")
        assert (
            ssl["EMAIL_PORT"] == 465
            and ssl["EMAIL_USE_SSL"]
            and not ssl["EMAIL_USE_TLS"]
        )

    def test_other_schemes_are_refused(self):
        with pytest.raises(ImproperlyConfigured, match="smtp://"):
            boot.email_url("https://mail.example.org")


def settings_in_a_fresh_interpreter(**env):
    """Import the settings in a process started with exactly ``env`` on top
    of a minimal base, and report what it saw, or how it failed."""
    code = (
        "import json; from django.conf import settings as s;"
        "print(json.dumps({k: getattr(s, k, None) for k in ("
        "'EMAIL_HOST','EMAIL_PORT','EMAIL_USE_TLS','USE_OBJECT_STORAGE','USE_SPACES')}))"
    )
    base = {
        "PATH": os.environ.get("PATH", ""),
        "DJANGO_SETTINGS_MODULE": "portal.settings",
    }
    done = subprocess.run(
        [sys.executable, "-c", code],
        env={**base, **env},
        capture_output=True,
        text=True,
    )
    if done.returncode:
        return {"error": done.stderr.strip()}
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestAtBoot:
    def test_production_without_the_services_refuses_to_start(self):
        found = settings_in_a_fresh_interpreter(
            SECRET_KEY="s", DATABASE_URL="postgresql://x"
        )
        assert "cannot start" in found["error"]
        assert "DJANGO_ALLOWED_HOSTS" in found["error"]

    def test_production_with_everything_starts_and_reads_email_url(self):
        found = settings_in_a_fresh_interpreter(**FULL)
        assert found["EMAIL_HOST"] == "mail.example.org"
        assert found["EMAIL_PORT"] == 587 and found["EMAIL_USE_TLS"] is True
        assert found["USE_OBJECT_STORAGE"] is False

    def test_debug_needs_only_the_secret_key_and_use_spaces_still_works(self):
        found = settings_in_a_fresh_interpreter(
            SECRET_KEY="s", DEBUG="1", USE_SPACES="true", AWS_STORAGE_BUCKET_NAME="b"
        )
        assert found["USE_OBJECT_STORAGE"] is True and found["USE_SPACES"] == "true"
