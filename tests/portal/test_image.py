"""The container image: slim by default, full by build argument, and a
collectstatic step that does not need the services."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_slim_is_the_default_flavour():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert 'ARG WHISPER_MODEL=""' in dockerfile
    assert "download_model('$WHISPER_MODEL'" in dockerfile  # full, on request


def test_collectstatic_in_the_image_skips_the_boot_check():
    dockerfile = (ROOT / "Dockerfile").read_text()
    at = dockerfile.index("python manage.py collectstatic")
    step = dockerfile[max(0, at - 400) : at]  # noqa: E203
    assert "BOOT_CHECK=0" in step and "SECRET_KEY=build-only" in step
    assert "DJANGO_SECRET_KEY" not in dockerfile  # the settings read SECRET_KEY
