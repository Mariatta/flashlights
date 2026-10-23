"""The health route the hosts probe: a bare 200, whatever the Host header,
with no database query."""

import pytest
from django.conf import settings

from portal import health

pytestmark = pytest.mark.django_db

PROBE_HOST = "10.244.3.17:8000"  # a pod address, never in ALLOWED_HOSTS


def test_the_middleware_runs_first():
    """Anything ahead of it would read the Host header and answer 400."""
    assert settings.MIDDLEWARE[0] == "portal.health.HealthCheckMiddleware"


def test_a_probe_from_an_unknown_host_gets_200(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get("/_health/", HTTP_HOST=PROBE_HOST)
    assert response.status_code == 200
    assert response.content == b"ok\n"
    assert response["Content-Type"] == "text/plain"
    assert response["Cache-Control"] == "no-store"


def test_without_the_trailing_slash_too(client):
    assert client.get("/_health", HTTP_HOST=PROBE_HOST).status_code == 200


def test_head_works_for_monitors_that_use_it(client):
    response = client.head("/_health/", HTTP_HOST=PROBE_HOST)
    assert response.status_code == 200
    assert response.content == b""


def test_other_methods_are_refused(client):
    response = client.post("/_health/", HTTP_HOST=PROBE_HOST)
    assert response.status_code == 405
    assert response["Allow"] == "GET, HEAD"


def test_only_the_health_path_skips_the_host_check(client):
    """The bypass is for the probe alone; every other path keeps Django's
    host check, which is what stops a request claiming to be a site it is
    not."""
    assert client.get("/", HTTP_HOST=PROBE_HOST).status_code == 400
    assert client.get("/_healthy/", HTTP_HOST=PROBE_HOST).status_code == 400


def test_the_paths_are_the_ones_the_hosts_are_told():
    assert health.PATHS == ("/_health/", "/_health")
