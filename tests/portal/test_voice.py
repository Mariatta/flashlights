"""The voice rules that a test can hold: sentence case on the chrome, no
exclamation marks in what we send, "Remember me"."""

import re
from pathlib import Path

import pytest
from django.urls import reverse

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
TITLE_CASE = re.compile(r'\{% trans "([A-Z][a-z]+ (?:[A-Z][a-z]+ ?){1,4})" %\}')
PROPER = {"Code of Conduct", "Terms of Service", "Google Calendar"}


def test_short_labels_are_sentence_case():
    for path in TEMPLATES.rglob("*.html"):
        for label in TITLE_CASE.findall(path.read_text()):
            assert label in PROPER or label.split()[1][0].islower(), f"{path}: {label}"


def test_emails_do_not_shout():
    for path in (TEMPLATES / "emails").rglob("*.md"):
        text = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", "", path.read_text())
        assert "!" not in text.replace("⚠️", ""), path


@pytest.mark.django_db
def test_sign_in_page_says_remember_me_and_sign_out(client, portal_user, conference):
    content = client.get(reverse("account_login")).content.decode()
    assert "Remember me" in content and "Remember Me" not in content
    client.force_login(portal_user)
    content = client.get(reverse("portal_stats")).content.decode()
    assert "Sign out" in content and "Sign Out" not in content
