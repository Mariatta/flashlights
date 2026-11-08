"""A person who did not get the verification email asks for a new code from
the code page, instead of signing up again or writing to an organiser."""

import re

import pytest
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed

SIGNUP = {
    "username": "newuser",
    "email": "newuser@example.com",
    "first_name": "New",
    "last_name": "User",
    "password1": "a-long-enough-password",
    "password2": "a-long-enough-password",
    "coc_agreement": "on",
    "tos_agreement": "on",
}


def code_in(message):
    """The code on its own line of a verification email: four characters, a
    dash, four characters, as allauth writes them."""
    return re.search(r"\n\n([A-Z0-9]{4}-[A-Z0-9]{4})\n", message.body).group(1)


@pytest.fixture
def code_page(client, captcha_solution):
    """A client that just signed up and sits on the code page, one email sent."""
    response = client.post(reverse("account_signup"), {**SIGNUP, **captcha_solution})
    assert response.status_code == 302
    assert len(mail.outbox) == 1
    return client


@pytest.fixture
def url():
    return reverse("account_email_verification_sent")


def test_code_page_offers_a_new_code(code_page, url):
    response = code_page.get(url)
    assertContains(response, "Send me a new code")
    assertContains(response, 'name="action" value="resend"')


def test_a_new_code_replaces_the_old_one(code_page, url, django_user_model):
    old = code_in(mail.outbox[0])
    cache.clear()  # the ten-second spacing between emails has its own test
    response = code_page.post(url, {"action": "resend"})
    assert response.status_code == 302 and response.url == url
    assert len(mail.outbox) == 2
    new = code_in(mail.outbox[1])
    assert new != old
    assertContains(code_page.post(url, {"code": old}), "Incorrect code.")
    assert code_page.post(url, {"code": new}).status_code == 302
    user = django_user_model.objects.get(username="newuser")
    assert user.emailaddress_set.get().verified


def test_after_two_new_codes_the_button_is_gone(code_page, url):
    for _ in range(2):
        cache.clear()
        assert code_page.post(url, {"action": "resend"}).status_code == 302
    assert len(mail.outbox) == 3
    assertNotContains(code_page.get(url), "Send me a new code")
    cache.clear()
    # A third request is read as an empty code, not as a resend.
    assert code_page.post(url, {"action": "resend"}).status_code == 200
    assert len(mail.outbox) == 3


def test_asking_again_within_ten_seconds_shows_the_wait_page(code_page, url):
    # The signup email went out a moment ago, so allauth refuses a second one.
    response = code_page.post(url, {"action": "resend"})
    assert response.status_code == 429
    assertTemplateUsed(response, "429.html")
    assertContains(response, "Please wait a moment", status_code=429)
    assert len(mail.outbox) == 1
