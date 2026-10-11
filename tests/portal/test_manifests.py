"""app.json and heroku.yml describe the same instance the boot contract
checks: every mandatory variable is asked for or provisioned."""

import json
from pathlib import Path

import yaml

from portal import boot

ROOT = Path(__file__).resolve().parents[2]


def test_app_json_asks_for_every_mandatory_variable():
    app = json.loads((ROOT / "app.json").read_text())
    provided = set(app["env"]) | {"DATABASE_URL", "REDIS_URL"}  # the add-ons
    for names, reason in boot.PRODUCTION:
        assert provided & set(names), (names, reason)
    assert app["env"]["SECRET_KEY"]["generator"] == "secret"
    assert app["formation"].keys() == {"web", "worker"}


def test_heroku_yml_runs_the_minimum_formation():
    config = yaml.safe_load((ROOT / "heroku.yml").read_text())
    assert config["run"]["worker"] == "sh bin/worker"
    assert "migrate" in config["release"]["command"][0]
    assert set(config["build"]["docker"]) == {"web", "worker"}
