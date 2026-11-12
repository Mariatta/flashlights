"""The visitor's address behind the host's proxy.

allauth keys its rate limits on the visitor's address and refuses a
request when it cannot find one. On Cabotage gunicorn listens on a unix
socket, so ``REMOTE_ADDR`` is empty and the address is only in the
``X-Forwarded-For`` the proxy adds.
"""

import pytest
from allauth.account.adapter import get_adapter
from django.test import RequestFactory, override_settings

#: The default, which tests/portal/test_boot.py checks in a fresh process;
#: pinned here so a TRUSTED_PROXY_COUNT in the shell does not change these.
pytestmark = pytest.mark.usefixtures("one_proxy")

CABOTAGE = {"REMOTE_ADDR": "", "HTTP_X_FORWARDED_FOR": "203.0.113.7"}


@pytest.fixture
def one_proxy(settings):
    settings.ALLAUTH_TRUSTED_PROXY_COUNT = 1


@pytest.fixture
def factory():
    return RequestFactory()


def test_the_address_is_read_from_the_proxy_with_no_peer_address(factory):
    request = factory.get("/accounts/login/", **CABOTAGE)
    assert get_adapter(request).get_client_ip(request) == "203.0.113.7"


def test_an_address_the_visitor_sent_ahead_of_the_proxys_is_ignored(factory):
    request = factory.get(
        "/accounts/login/",
        REMOTE_ADDR="",
        HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.7",
    )
    assert get_adapter(request).get_client_ip(request) == "203.0.113.7"


def test_without_a_proxy_the_peer_address_is_used(factory):
    request = factory.get("/accounts/login/", REMOTE_ADDR="192.0.2.9")
    assert get_adapter(request).get_client_ip(request) == "192.0.2.9"


@override_settings(ALLAUTH_TRUSTED_CLIENT_IP_HEADER="CF-Connecting-IP")
def test_a_named_header_wins_over_x_forwarded_for(factory):
    request = factory.get(
        "/accounts/login/", HTTP_CF_CONNECTING_IP="192.0.2.44", **CABOTAGE
    )
    assert get_adapter(request).get_client_ip(request) == "192.0.2.44"


@pytest.mark.django_db
def test_signing_in_through_the_proxy_is_not_refused(client):
    response = client.post(
        "/accounts/login/",
        {"login": "nobody", "password": "wrong"},
        **CABOTAGE,
    )
    assert response.status_code == 200
    assert response.context["form"].errors
