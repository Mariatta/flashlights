"""The demo preset switcher, ``scripts/preset.py``."""

import re
import subprocess
from pathlib import Path

import psycopg2
import pytest

from scripts import preset

ROOT = Path(__file__).resolve().parent.parent


def test_the_documented_settings_example_reads_cleanly(tmp_path):
    """Copying the setup guide's ``.preset-settings`` block gives values a
    server can use: a remark on a value's line would become part of it."""
    setup = (ROOT / "docs/developer/setup.md").read_text()
    block = re.search(r"# \.preset-settings\n(.*?)\n\n", setup, re.S).group(1)
    path = tmp_path / ".preset-settings"
    path.write_text(block)
    values = preset.read_env_file(path)
    assert values["DJANGO_EMAIL_HOST"] == "localhost"
    assert values["DJANGO_EMAIL_PORT"] == "1025"


def write_preset(folder, name, env=""):
    path = folder / name
    path.mkdir(parents=True)
    (path / "seed.py").write_text("def run(stdout):\n    pass\n")
    if env:
        (path / "env").write_text(env)
    return path


class TestSettings:
    def test_env_file_lines(self, tmp_path):
        path = tmp_path / "settings"
        assert preset.read_env_file(path) == {}
        path.write_text("# a remark\n\nA = 1\nB='two'\nC=\"three\"\nnot a line\n")
        assert preset.read_env_file(path) == {"A": "1", "B": "two", "C": "three"}

    def test_the_environment_wins_for_the_scripts_own_keys(self, tmp_path, monkeypatch):
        path = tmp_path / ".preset-settings"
        path.write_text("PRESET_PORT=9000\nREDIS_URL=redis://x\n")
        monkeypatch.setattr(preset, "SETTINGS_FILE", path)
        monkeypatch.setenv("PRESET_PORT", "9100")
        assert preset.settings() == {"PRESET_PORT": "9100", "REDIS_URL": "redis://x"}

    def test_presets_from_the_repository_and_the_path(self, tmp_path):
        write_preset(tmp_path / "extra", "vancouver")
        write_preset(tmp_path / "extra", "bare")  # the repository's comes first
        (tmp_path / "extra" / "not-a-preset").mkdir()
        found = preset.preset_dirs(
            {"PRESETS_PATH": f"{tmp_path / 'extra'}{':'}{tmp_path / 'missing'}"}
        )
        assert found["bare"] == preset.ROOT / "presets" / "bare"
        assert found["vancouver"] == tmp_path / "extra" / "vancouver"
        assert "not-a-preset" not in found

    def test_one_database_per_preset(self):
        assert preset.database_name("PyLadies Vancouver!") == (
            "flashlights_pyladies_vancouver"
        )
        assert preset.database_url({}, "bare") == (
            "postgresql://flashlights:flashlights@localhost:5433/flashlights_bare"
        )
        assert preset.database_url({"PRESET_DB": "postgresql://u@h:1/"}, "x") == (
            "postgresql://u@h:1/flashlights_x"
        )

    def test_server_env_layers(self, tmp_path, monkeypatch):
        folder = write_preset(tmp_path, "demo", env="BRAND_NAME=Demo\nDEBUG=0\n")
        monkeypatch.setenv("HOME_THING", "kept")
        env = preset.server_env(
            {"PRESET_PORT": "9000", "DJANGO_EMAIL_HOST": "localhost"}, folder
        )
        assert env["HOME_THING"] == "kept"
        assert env["SECRET_KEY"] == "preset-dev-only"
        assert env["DJANGO_EMAIL_HOST"] == "localhost"
        assert "PRESET_PORT" not in env
        assert env["BRAND_NAME"] == "Demo" and env["DEBUG"] == "0"
        assert env["DATABASE_URL"].endswith("/flashlights_demo")


class FakeCursor:
    def __init__(self, log, row):
        self.log, self.row, self.description = log, row, None

    def execute(self, sql, params=None):
        self.log.append((sql, params))
        self.description = ("x",) if sql.startswith("SELECT") else None

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, log, row):
        self.log, self.row, self.autocommit, self.closed = log, row, False, False

    def cursor(self):
        assert self.autocommit
        return FakeCursor(self.log, self.row)

    def close(self):
        self.closed = True


@pytest.fixture
def postgres(monkeypatch):
    """psycopg2 on a fake server: the statements run, and the row a SELECT
    answers (``state["row"]``)."""
    state = {"log": [], "row": None, "urls": []}

    def connect(url):
        state["urls"].append(url)
        return FakeConnection(state["log"], state["row"])

    monkeypatch.setattr(psycopg2, "connect", connect)
    return state


@pytest.fixture
def calls(monkeypatch, tmp_path):
    """subprocess, os.kill and the state folder, recorded."""
    state = {"run": [], "popen": [], "killed": [], "pids": ""}

    class Result:
        def __init__(self, stdout=""):
            self.stdout = stdout

    def run(args, **kwargs):
        state["run"].append(args)
        return Result(state["pids"] if args[0] == "pgrep" else "")

    def popen(args, **kwargs):
        state["popen"].append(args)

    monkeypatch.setattr(preset.subprocess, "run", run)
    monkeypatch.setattr(preset.subprocess, "Popen", popen)
    monkeypatch.setattr(preset.os, "kill", lambda pid, sig: state["killed"].append(pid))
    monkeypatch.setattr(preset.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(preset, "STATE", tmp_path / ".state")
    return state


class TestDatabases:
    def test_statements_run_on_the_postgres_database(self, postgres):
        postgres["row"] = (1,)
        assert preset.database_exists({}, "bare") is True
        sql, params = postgres["log"][0]
        assert "pg_database" in sql and params == ["flashlights_bare"]
        assert postgres["urls"][0].endswith("/postgres")
        assert preset.admin_sql({}, "DROP DATABASE x") is None

    def test_reset_builds_the_database_and_loads_the_preset(self, postgres, calls):
        folder = preset.ROOT / "presets" / "bare"
        preset.reset({}, folder)
        statements = [sql for sql, _ in postgres["log"]]
        assert statements == [
            'DROP DATABASE IF EXISTS "flashlights_bare" WITH (FORCE)',
            'CREATE DATABASE "flashlights_bare"',
        ]
        commands = [args[2] for args in calls["run"] if args[0] != "pgrep"]
        assert commands == ["migrate", "createcachetable", "load_preset"]

    def test_a_preset_that_fails_to_load_leaves_no_database(
        self, postgres, calls, monkeypatch
    ):
        def fail(env, *args):
            raise subprocess.CalledProcessError(1, args)

        monkeypatch.setattr(preset, "manage", fail)
        with pytest.raises(subprocess.CalledProcessError):
            preset.reset({}, preset.ROOT / "presets" / "bare")
        assert postgres["log"][-1][0].startswith("DROP DATABASE")

    def test_drop(self, postgres, calls, capsys):
        preset.drop({}, preset.ROOT / "presets" / "bare")
        assert "Dropped flashlights_bare." in capsys.readouterr().out


class TestServer:
    def test_manage_runs_the_projects_manage_py(self, monkeypatch, capsys):
        seen = {}

        def run(args, **kwargs):
            seen.update(args=args, **kwargs)

        monkeypatch.setattr(preset.subprocess, "run", run)
        preset.manage({"A": "1"}, "migrate", "-v", "0")
        assert seen["args"][1:] == ["manage.py", "migrate", "-v", "0"]
        assert seen["env"] == {"A": "1"} and seen["check"] is True
        assert "+ manage.py migrate -v 0" in capsys.readouterr().out

    def test_stop_stops_whatever_serves_the_port(self, calls, capsys):
        preset.stop({})
        assert calls["killed"] == []
        calls["pids"] = "12\n34\n"
        preset.stop({"PRESET_PORT": "9000"})
        assert calls["killed"] == [12, 34]
        assert calls["run"][-1][-1] == "manage.py runserver 127.0.0.1:9000"
        assert "Stopped the server on 127.0.0.1:9000." in capsys.readouterr().out

    def test_serve_starts_the_server_and_remembers_the_preset(self, calls, capsys):
        preset.serve({}, preset.ROOT / "presets" / "bare")
        assert calls["popen"][0][-2:] == ["runserver", "127.0.0.1:8002"]
        assert (preset.STATE / "preset-current").read_text() == "bare"
        assert "Serving bare at http://127.0.0.1:8002/" in capsys.readouterr().out

    def test_list_marks_the_current_and_the_built(
        self, postgres, calls, capsys, monkeypatch
    ):
        monkeypatch.setattr(preset, "SETTINGS_FILE", preset.STATE / "none")
        preset.main(["list"])
        assert "not built" in capsys.readouterr().out
        preset.STATE.mkdir()
        (preset.STATE / "preset-current").write_text("bare")
        postgres["row"] = (1,)
        preset.main(["list"])
        lines = capsys.readouterr().out.splitlines()
        assert any(line.startswith("* bare") and " built " in line for line in lines)


class TestMain:
    @pytest.fixture(autouse=True)
    def no_settings_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(preset, "SETTINGS_FILE", tmp_path / "none")
        monkeypatch.delenv("PRESETS_PATH", raising=False)

    def test_an_unknown_preset_is_refused(self, capsys):
        with pytest.raises(SystemExit):
            preset.main(["use", "summit"])
        assert "name a preset: bare, empty" in capsys.readouterr().err
        with pytest.raises(SystemExit):
            preset.main(["reset"])

    def test_no_presets_at_all(self, monkeypatch, capsys):
        monkeypatch.setattr(preset, "preset_dirs", lambda config: {})
        with pytest.raises(SystemExit):
            preset.main(["serve", "bare"])
        assert "name a preset: none found" in capsys.readouterr().err

    def test_use_builds_only_what_is_missing(self, monkeypatch):
        done = []
        monkeypatch.setattr(
            preset, "reset", lambda config, folder: done.append("reset")
        )
        monkeypatch.setattr(
            preset, "serve", lambda config, folder: done.append("serve")
        )
        monkeypatch.setattr(preset, "database_exists", lambda config, name: False)
        preset.main(["use", "bare"])
        monkeypatch.setattr(preset, "database_exists", lambda config, name: True)
        preset.main(["use", "bare"])
        assert done == ["reset", "serve", "serve"]

    def test_the_other_commands(self, monkeypatch):
        done = []
        for name in ("reset", "serve", "drop", "stop"):
            monkeypatch.setattr(
                preset, name, lambda *args, name=name: done.append(name)
            )
        for command in ("reset", "serve", "drop"):
            preset.main([command, "empty"])
        preset.main(["stop"])
        assert done == ["reset", "serve", "drop", "stop"]
