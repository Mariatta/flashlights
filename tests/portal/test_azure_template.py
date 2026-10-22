"""The Azure template passes the boot contract's variables to every process."""

import re
from pathlib import Path

from portal import boot

ROOT = Path(__file__).resolve().parents[2]


def test_every_mandatory_variable_reaches_the_containers():
    bicep = (ROOT / "deploy/azure/main.bicep").read_text()
    names = set(re.findall(r"\{ name: '([A-Z0-9_]+)'", bicep))
    for alternatives, reason in boot.PRODUCTION:
        assert names & set(alternatives), (alternatives, reason)
    assert "SECRET_KEY" in names
    assert bicep.count("env: env") == 3  # web, worker, release


def test_params_example_names_every_required_parameter():
    bicep = (ROOT / "deploy/azure/main.bicep").read_text()
    required = {m.group(1) for m in re.finditer(r"^param (\w+) \w+$", bicep, re.M)}
    example = (ROOT / "deploy/azure/params.example.json").read_text()
    for name in required:
        assert f'"{name}"' in example, name


def test_the_secrets_are_encoded_into_the_connection_urls():
    """A password or key with '@' or '/' in it would otherwise be read as
    the host; the template encodes both as URL components."""
    bicep = (ROOT / "deploy/azure/main.bicep").read_text()
    assert "${uriComponent(postgresPassword)}@" in bicep
    assert "${uriComponent(redis.listKeys().primaryKey)}@" in bicep
    assert "${postgresPassword}@" not in bicep


def test_the_web_app_is_probed_on_the_health_route():
    """Startup, readiness and liveness, all against the route that answers
    without a Host header; the worker has no port and no probes."""
    bicep = (ROOT / "deploy/azure/main.bicep").read_text()
    _, web, rest = (
        bicep.partition("resource web ")[0],
        *bicep.partition("resource web ")[1:],
    )
    web, _, rest = rest.partition("resource worker ")
    worker, _, _ = rest.partition("resource release ")
    assert web.count("httpGet: { path: '/_health/', port: 8000 }") == 3
    for kind in ("Startup", "Readiness", "Liveness"):
        assert f"type: '{kind}'" in web
    assert "probes" not in worker
