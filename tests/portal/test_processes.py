"""The worker process script: one worker, beat embedded unless told not to."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_worker(tmp_path, **env):
    """Run bin/worker with a fake ``celery`` on PATH that prints its arguments."""
    fake = tmp_path / "celery"
    fake.write_text('#!/bin/sh\necho "$@"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    done = subprocess.run(
        ["sh", "bin/worker"],
        cwd=ROOT,
        env={"PATH": f"{tmp_path}:{os.environ['PATH']}", **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_the_script_is_executable_and_valid_shell():
    script = ROOT / "bin/worker"
    assert script.stat().st_mode & stat.S_IXUSR
    subprocess.run(["sh", "-n", str(script)], check=True)


def test_the_minimum_formation_serves_every_queue_with_beat(tmp_path):
    assert run_worker(tmp_path) == "-A portal worker -Q celery,media -B --loglevel=info"


@pytest.mark.parametrize("off", ["0", "false", "no", "off"])
def test_a_scaled_formation_leaves_beat_to_its_own_process(tmp_path, off):
    line = run_worker(tmp_path, CELERY_EMBED_BEAT=off, CELERY_WORKER_QUEUES="celery")
    assert line == "-A portal worker -Q celery --loglevel=info"


def test_the_procfile_and_compose_run_it():
    assert "worker: sh bin/worker" in (ROOT / "Procfile").read_text()
    compose = (ROOT / "compose.yml").read_text()
    assert "command: sh bin/worker" in compose and "  beat:\n" not in compose


def test_compose_probes_web_on_the_health_route():
    """The development stack is the plain-server template, so its web
    service carries the healthcheck the guide tells readers to keep."""
    compose = (ROOT / "compose.yml").read_text()
    web = compose.partition("\n  web:\n")[2].partition("\n  celery:\n")[0]
    assert "healthcheck:" in web
    assert "os.environ.get('PORT', '8000') + '/_health/'" in web
