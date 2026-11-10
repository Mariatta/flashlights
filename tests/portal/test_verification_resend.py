"""A person who did not get the verification email asks for a new code from
the code page, instead of signing up again or writing to an organizer."""

import re
import time

import pytest
from allauth.account.forms import ConfirmPasswordResetCodeForm
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import path, reverse
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed

from portal import urls as portal_urls
from portal.templatetags import portal_extras
from portal.templatetags.portal_extras import (
    code_lifetime_minutes,
    minutes_seconds,
    new_code_wait_seconds,
)

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


def test_without_the_button_the_page_still_says_what_to_do(code_page, url):
    for _ in range(2):
        cache.clear()
        code_page.post(url, {"action": "resend"})
    response = code_page.get(url)
    assertNotContains(response, "Send me a new code")
    assertContains(response, "Check your spam folder.")
    assertContains(response, "choose Cancel and sign in again")


def test_cancel_then_sign_in_again_sends_a_new_code(code_page, url):
    code_page.post(reverse("account_logout"))
    cache.clear()
    response = code_page.post(
        reverse("account_login"),
        {"login": SIGNUP["username"], "password": SIGNUP["password1"]},
    )
    assert response.status_code == 302 and response.url == url
    assert len(mail.outbox) == 2
    assertContains(code_page.get(url), "Send me a new code")


def test_sign_in_code_page_has_no_resend_or_hint(client, portal_user):
    client.post(reverse("account_request_login_code"), {"email": portal_user.email})
    response = client.get(reverse("account_confirm_login_code"))
    assert response.status_code == 200
    assertNotContains(response, "Send me a new code")
    assertNotContains(response, "spam folder")


def test_adding_an_address_while_signed_in_offers_no_sign_in_again(client, portal_user):
    client.force_login(portal_user)
    client.post(
        reverse("account_email"), {"action_add": "", "email": "second@example.com"}
    )
    response = client.get(reverse("account_email_verification_sent"))
    assertContains(response, "Check your spam folder")
    assertNotContains(response, "choose Cancel and sign in again")
    assertContains(response, f'href="{reverse("account_email")}"')


def test_code_page_says_how_long_the_code_works(code_page, url):
    assertContains(
        code_page.get(url),
        "The code works for up to 15 minutes, so please enter it soon.",
    )


def test_sign_in_code_page_says_how_long_the_code_works(client, portal_user):
    client.post(reverse("account_request_login_code"), {"email": portal_user.email})
    response = client.get(reverse("account_confirm_login_code"))
    assertContains(response, "The code works for 3 minutes, so please")
    assertNotContains(response, "expires shortly")


def test_code_lifetime_follows_the_setting(settings):
    settings.ACCOUNT_LOGIN_BY_CODE_TIMEOUT = 60
    assert code_lifetime_minutes("login") == 1
    settings.ACCOUNT_LOGIN_BY_CODE_TIMEOUT = 20
    assert code_lifetime_minutes("login") == 1
    settings.ACCOUNT_PASSWORD_RESET_BY_CODE_TIMEOUT = 600
    assert code_lifetime_minutes("password_reset") == 10
    # Part minutes round down: the page never promises more than allauth allows.
    settings.ACCOUNT_LOGIN_BY_CODE_TIMEOUT = 150
    assert code_lifetime_minutes("login") == 2
    settings.ACCOUNT_LOGIN_BY_CODE_TIMEOUT = 90
    assert code_lifetime_minutes("login") == 1


#: The project's URLs plus the reset-code page, which allauth registers only
#: when reset by code is on; Flashlights resets by link.
urlpatterns = [
    path(
        "accounts/password/reset/code/confirm/",
        lambda request: None,
        name="account_confirm_password_reset_code",
    ),
    *portal_urls.urlpatterns,
]


@pytest.mark.urls(__name__)
def test_password_reset_code_page_says_how_long_the_code_works(rf):
    """An instance that turns on reset by code gets this template."""
    request = rf.get("/")
    request.user = AnonymousUser()
    html = render_to_string(
        "account/confirm_password_reset_code.html",
        {
            "form": ConfirmPasswordResetCodeForm(code="ABCD-EFGH"),
            "email": "a@example.com",
        },
        request=request,
    )
    assert "The code works for 3 minutes, so please" in html
    assert "expires shortly" not in html


def test_right_after_an_email_the_page_counts_down(code_page, url):
    response = code_page.get(url)
    assertContains(response, "We sent a code just now.")
    assertContains(response, "js/new-code-countdown.")
    wait = int(re.search(r'data-new-code-wait="(\d+)"', response.text).group(1))
    assert 1 <= wait <= 10
    assertContains(response, f"<span data-new-code-clock>0:{wait:02d}</span>")


def test_once_allauth_would_send_again_there_is_no_countdown(code_page, url):
    cache.clear()
    response = code_page.get(url)
    assertNotContains(response, "data-new-code-wait")
    assertNotContains(response, "We sent a code just now.")
    assertContains(response, "Send me a new code")


def test_no_countdown_once_the_new_codes_are_used_up(code_page, url):
    for _ in range(2):
        cache.clear()
        assert code_page.post(url, {"action": "resend"}).status_code == 302
    # The last email went out a moment ago, but there is no button to wait for.
    assertNotContains(code_page.get(url), "data-new-code-wait")


def test_wait_is_read_from_allauths_record(code_page, rf, monkeypatch):
    context = {"request": rf.get("/")}
    assert 1 <= new_code_wait_seconds(context, SIGNUP["email"]) <= 10
    # The limit is per address, whatever the case it was typed in.
    assert new_code_wait_seconds(context, SIGNUP["email"].upper()) >= 1
    assert new_code_wait_seconds(context, "someone-else@example.com") == 0
    later = time.time() + 11
    monkeypatch.setattr(portal_extras.time, "time", lambda: later)
    assert new_code_wait_seconds(context, SIGNUP["email"]) == 0


def test_wait_needs_a_request_and_an_address():
    assert new_code_wait_seconds({}, SIGNUP["email"]) == 0
    assert new_code_wait_seconds({"request": object()}, "") == 0


@pytest.mark.parametrize(
    "seconds, clock", [(0, "0:00"), (8, "0:08"), (10, "0:10"), (150, "2:30")]
)
def test_minutes_seconds(seconds, clock):
    assert minutes_seconds(seconds) == clock


def test_verification_email_says_how_long_the_code_works(code_page):
    assert (
        "The code works for up to 15 minutes. If it has stopped working, sign in again"
        in mail.outbox[0].body
    )


def test_sign_in_code_email_says_how_long_the_code_works(client, portal_user):
    client.post(reverse("account_request_login_code"), {"email": portal_user.email})
    assert "The code works for 3 minutes." in mail.outbox[-1].body


def test_password_reset_code_email_says_how_long_the_code_works(settings):
    settings.ACCOUNT_PASSWORD_RESET_BY_CODE_TIMEOUT = 600
    body = render_to_string(
        "account/email/password_reset_code_message.txt", {"code": "ABCD-EFGH"}
    )
    assert "ABCD-EFGH" in body
    assert "The code works for 10 minutes." in body
