"""The web process binds the way the host expects."""

import io
import runpy
from pathlib import Path

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


def test_when_ready_writes_the_marker(monkeypatch):
    monkeypatch.setattr("os.path.isdir", lambda path: False)
    conf = runpy.run_path(str(CONF))
    opened = []

    def fake_open(path, mode):
        opened.append((path, mode))
        return io.StringIO()

    monkeypatch.setattr("builtins.open", fake_open)
    conf["when_ready"](server=None)
    assert opened == [("/tmp/app-initialized", "w")]
