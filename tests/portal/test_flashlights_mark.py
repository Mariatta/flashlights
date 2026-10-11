"""Flashlights' own mark: in the footer, on the share card, in emails."""

import io

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core import mail
from django.urls import reverse
from PIL import Image

from common.markdown_emails import deliver_markdown_email, wrap_html


def test_mark_files_ship_clean():
    for name in ("mark-night.svg", "mark-light.svg"):
        text = open(finders.find(f"img/flashlights/{name}")).read()
        assert "<metadata" not in text and "googleapis" not in text
        assert "rotate(-32 50 50)" in text


@pytest.mark.django_db
def test_footer_carries_the_lockup(client, conference):
    content = client.get(reverse("portal_stats")).content.decode()
    assert 'class="flashlights-lockup"' in content
    assert 'class="flashlights-name">Flashlights</span>' in content
    assert "File an issue in the repository" in content


def test_share_card_draws_the_mark():
    image = Image.open(io.BytesIO(settings.BRAND.share_card_png())).convert("RGB")
    # Beam pixels of the mark's lens sit in the bottom band, left of centre.
    band = image.crop((500, 540, 640, 600))
    beam = sum(
        1 for p in band.getdata() if p[0] > 240 and 190 < p[1] < 230 and p[2] < 90
    )
    assert beam > 20


@pytest.mark.django_db
def test_html_email_is_wrapped_in_the_instance_chrome():
    html = wrap_html("<p>Hello <b>there</b></p>")
    assert settings.BRAND.short_name in html
    assert f"background:{settings.BRAND.primary}" in html
    assert "<p>Hello <b>there</b></p>" in html
    deliver_markdown_email("Subject", ["a@example.org"], "<p>Body</p>", "Body")
    alternative = mail.outbox[0].alternatives[0]
    assert alternative[1] == "text/html"
    assert (
        "<p>Body</p>" in alternative[0] and settings.BRAND.short_name in alternative[0]
    )
