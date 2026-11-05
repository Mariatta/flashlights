"""The web process binds the way the host expects, and keeps the hosts'
probes out of its access log."""

import io
import logging
import runpy
from pathlib import Path
from types import SimpleNamespace

from portal import health

CONF = Path(__file__).resolve().parents[2] / "config" / "gunicorn.conf.py"


def test_binds_to_port_on_an_ordinary_host(monkeypatch):
    """Heroku, Azure and a plain server hand the process a port."""
    monkeypatch.setenv("PORT", "5123")
    monkeypatch.setattr("os.path.isdir", lambda path: False)
    conf = runpy.run_path(str(CONF))
    assert conf["bind"] == "0.0.0.0:5123"


def test_port_defaults_to_8000(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr("os.path.isdir", lambda path: False)
    assert runpy.run_path(str(CONF))["bind"] == "0.0.0.0:8000"


def test_binds_to_the_socket_on_cabotage(monkeypatch):
    """Cabotage mounts its socket directory and waits for the marker file."""
    monkeypatch.setenv("PORT", "5123")
    monkeypatch.setattr("os.path.isdir", lambda path: path == "/var/run/cabotage")
    conf = runpy.run_path(str(CONF))
    assert conf["bind"] == "unix:/var/run/cabotage/cabotage.sock"


def fake_server():
    return SimpleNamespace(
        log=SimpleNamespace(access_log=logging.Logger("test.access"))
    )


def test_when_ready_writes_the_marker(monkeypatch):
    monkeypatch.setattr("os.path.isdir", lambda path: False)
    conf = runpy.run_path(str(CONF))
    opened = []

    def fake_open(path, mode):
        opened.append((path, mode))
        return io.StringIO()

    monkeypatch.setattr("builtins.open", fake_open)
    conf["when_ready"](fake_server())
    assert opened == [("/tmp/app-initialized", "w")]


def access_record(path):
    """What gunicorn logs per request: the format string plus the atoms,
    ``U`` being the URL path."""
    return logging.LogRecord(
        "gunicorn.access",
        logging.INFO,
        "",
        0,
        "%(h)s %(r)s",
        {"U": path, "h": "-"},
        None,
    )


def test_when_ready_keeps_the_probes_out_of_the_access_log(monkeypatch):
    monkeypatch.setattr("os.path.isdir", lambda path: False)
    monkeypatch.setattr("builtins.open", lambda path, mode: io.StringIO())
    conf = runpy.run_path(str(CONF))
    server = fake_server()
    conf["when_ready"](server)
    (probe_filter,) = server.log.access_log.filters
    server.log.access_log.removeFilter(probe_filter)
    for path in health.PATHS:
        assert not probe_filter.filter(access_record(path))
    assert probe_filter.filter(access_record("/"))
    assert probe_filter.filter(access_record("/_healthy/"))


def test_the_filter_leaves_other_log_lines_alone():
    conf = runpy.run_path(str(CONF))
    record = logging.LogRecord(
        "gunicorn.error", logging.INFO, "", 0, "Booting worker %s", (1,), None
    )
    assert conf["NotAHealthProbe"]().filter(record)


def test_the_paths_match_the_app(monkeypatch):
    """The config repeats the paths rather than importing the app."""
    assert runpy.run_path(str(CONF))["HEALTH_PATHS"] == health.PATHS
