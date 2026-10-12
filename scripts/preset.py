#!/usr/bin/env python
"""Switch the local instance between demo presets.

Each preset gets its own database (``flashlights_<name>``), so switching is
instant and nothing is reseeded; ``reset`` rebuilds one from scratch.

    python scripts/preset.py list
    python scripts/preset.py use summit      # reset if missing, then serve
    python scripts/preset.py reset summit    # drop, migrate, load the preset
    python scripts/preset.py serve summit    # restart the dev server on it
    python scripts/preset.py drop summit
    python scripts/preset.py stop

Or through make: ``make preset PRESET=summit``, ``make preset-reset ...``.

A preset is a directory holding ``seed.py`` (``run(stdout)``, loaded by
``manage.py load_preset``) and an optional ``env`` file of KEY=value lines
for the branding. ``presets/`` in this repository ships the bare one; more
directories, such as private presets with a real community's data, join
through ``PRESETS_PATH`` (paths separated by ``:``).

Settings come from the environment or from ``.preset-settings`` at the
repository root (git-ignored, KEY=value lines):

    PRESETS_PATH   extra preset folders               (default: presets)
    PRESET_DB      Postgres URL without the database  (default: compose's)
    PRESET_HOST    PRESET_PORT                        (127.0.0.1, 8002)

Every other line of ``.preset-settings`` (DJANGO_EMAIL_HOST, REDIS_URL...)
is passed to the dev server, under the preset's own ``env``.
"""

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".state"
SETTINGS_FILE = ROOT / ".preset-settings"
DEFAULT_DB = "postgresql://flashlights:flashlights@localhost:5433"
SCRIPT_KEYS = {"PRESETS_PATH", "PRESET_DB", "PRESET_HOST", "PRESET_PORT"}
DEV_DEFAULTS = {
    "SECRET_KEY": "preset-dev-only",
    "DEBUG": "1",
    "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
}


def read_env_file(path):
    """KEY=value lines; blank lines and # comments skipped, quotes stripped."""
    values = {}
    if not path.is_file():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def settings():
    values = read_env_file(SETTINGS_FILE)
    for key in SCRIPT_KEYS:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def preset_dirs(config):
    folders = [ROOT / "presets"]
    for part in config.get("PRESETS_PATH", "").split(os.pathsep):
        if part.strip():
            folders.append(Path(part.strip()).expanduser())
    found = {}
    for folder in folders:
        if folder.is_dir():
            for child in sorted(folder.iterdir()):
                if (child / "seed.py").is_file():
                    found.setdefault(child.name, child)
    return found


def database_name(name):
    return "flashlights_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def database_url(config, name):
    base = urlsplit(config.get("PRESET_DB", DEFAULT_DB).rstrip("/"))
    return urlunsplit(base._replace(path="/" + database_name(name)))


def admin_sql(config, sql, params=None):
    """One statement on the server's ``postgres`` database, outside any
    transaction (CREATE and DROP DATABASE refuse to run inside one, and
    psycopg2's connection context manager opens one). Returns a row."""
    import psycopg2  # the project's driver, imported only when talking to Postgres

    base = urlsplit(config.get("PRESET_DB", DEFAULT_DB).rstrip("/"))
    connection = psycopg2.connect(urlunsplit(base._replace(path="/postgres")))
    connection.autocommit = True
    try:
        cursor = connection.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone() if cursor.description else None
    finally:
        connection.close()


def database_exists(config, name):
    row = admin_sql(
        config, "SELECT 1 FROM pg_database WHERE datname = %s", [database_name(name)]
    )
    return row is not None


def server_env(config, preset):
    env = dict(os.environ)
    env.update(DEV_DEFAULTS)
    env.update({k: v for k, v in config.items() if k not in SCRIPT_KEYS})
    env.update(read_env_file(preset / "env"))
    env["DATABASE_URL"] = database_url(config, preset.name)
    return env


def manage(env, *args):
    print("+ manage.py", " ".join(args), flush=True)
    subprocess.run([sys.executable, "manage.py", *args], cwd=ROOT, env=env, check=True)


def address(config):
    return config.get("PRESET_HOST", "127.0.0.1"), config.get("PRESET_PORT", "8002")


def stop(config):
    """Stop the dev server on the preset port, whichever preset it serves."""
    host, port = address(config)
    pattern = f"manage.py runserver {host}:{port}"
    result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    pids = [int(pid) for pid in result.stdout.split()]
    for pid in pids:
        os.kill(pid, signal.SIGTERM)
    if pids:
        time.sleep(1)
        print(f"Stopped the server on {host}:{port}.")


def reset(config, preset):
    stop(config)
    name = database_name(preset.name)
    admin_sql(config, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin_sql(config, f'CREATE DATABASE "{name}"')
    print(f"Created {name}.")
    env = server_env(config, preset)
    try:
        manage(env, "migrate", "--no-input", "-v", "0")
        manage(env, "createcachetable")
        manage(env, "load_preset", str(preset))
    except BaseException:
        # A half-built database would read as built to ``use``.
        admin_sql(config, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        print(f"Dropped {name}: the preset did not load.")
        raise


def serve(config, preset):
    stop(config)
    host, port = address(config)
    STATE.mkdir(exist_ok=True)
    log = STATE / "preset-server.log"
    with open(log, "w") as handle:
        subprocess.Popen(
            [sys.executable, "manage.py", "runserver", f"{host}:{port}"],
            cwd=ROOT,
            env=server_env(config, preset),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (STATE / "preset-current").write_text(preset.name)
    print(f"Serving {preset.name} at http://{host}:{port}/ (log: {log})")


def drop(config, preset):
    stop(config)
    admin_sql(
        config, f'DROP DATABASE IF EXISTS "{database_name(preset.name)}" WITH (FORCE)'
    )
    print(f"Dropped {database_name(preset.name)}.")


def show(config, presets):
    current_file = STATE / "preset-current"
    current = current_file.read_text().strip() if current_file.is_file() else ""
    for name, path in presets.items():
        built = "built" if database_exists(config, name) else "not built"
        mark = "*" if name == current else " "
        print(f"{mark} {name:24} {built:10} {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "command", choices=["list", "use", "reset", "serve", "drop", "stop"]
    )
    parser.add_argument("preset", nargs="?")
    args = parser.parse_args(argv)
    config = settings()
    presets = preset_dirs(config)
    if args.command == "list":
        return show(config, presets)
    if args.command == "stop":
        return stop(config)
    if not args.preset or args.preset not in presets:
        known = ", ".join(presets) or "none found"
        parser.error(f"name a preset: {known}")
    preset = presets[args.preset]
    if args.command == "use":
        if not database_exists(config, preset.name):
            reset(config, preset)
        return serve(config, preset)
    {"reset": reset, "serve": serve, "drop": drop}[args.command](config, preset)


if __name__ == "__main__":
    sys.exit(main())
