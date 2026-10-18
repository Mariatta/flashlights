"""Community apps: what EXTRA_APPS adds to the core and how."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse

from portal import community

APP = "tests.community_app"
PLAIN = "tests.community_plain"
APP_DIR = Path(__file__).resolve().parents[1] / "community_app"


class TestNames:
    def test_comma_separated_module_paths(self):
        assert community.names({"EXTRA_APPS": "a.b, c ,,"}) == ["a.b", "c"]

    def test_unset_or_blank_means_bare(self):
        assert community.names({}) == []
        assert community.names({"EXTRA_APPS": " "}) == []


class TestTemplateDirs:
    def test_an_app_with_templates_contributes_its_folder(self):
        assert community.template_dirs([APP]) == [APP_DIR / "templates"]

    def test_an_app_without_templates_contributes_nothing(self):
        assert community.template_dirs([PLAIN]) == []

    def test_an_app_that_cannot_be_imported_names_the_variable(self):
        with pytest.raises(ImproperlyConfigured, match="EXTRA_APPS names 'nope.app'"):
            community.template_dirs(["nope.app"])
        with pytest.raises(ImproperlyConfigured, match="tests.nothere"):
            community.template_dirs(["tests.nothere"])
        # A plain module is not a package either.
        with pytest.raises(ImproperlyConfigured, match="portal.community"):
            community.template_dirs(["portal.community"])


class TestUrlPrefix:
    def test_the_module_may_set_it_and_it_is_normalised(self):
        class Urls:
            prefix = "/summit"

        assert community.url_prefix("x.summit_app", Urls) == "summit/"
        Urls.prefix = ""
        assert community.url_prefix("x.summit_app", Urls) == ""

    def test_the_default_is_the_module_name_with_hyphens(self):
        assert community.url_prefix("x.summit_app", object()) == "summit-app/"


class TestUrlpatterns:
    def test_one_include_per_app_with_a_urls_module(self):
        patterns = community.urlpatterns([APP, PLAIN, "tests"])
        assert [str(p.pattern) for p in patterns] == ["community/", "community-plain/"]
        assert patterns[0].namespace == "community_app"
        assert patterns[1].namespace is None

    def test_an_app_that_is_not_a_package_has_no_urls(self):
        assert community.urlpatterns(["portal.community"]) == []


@pytest.mark.django_db
class TestServing:
    def test_the_apps_pages_answer_under_their_prefixes(self, client):
        with override_settings(
            ROOT_URLCONF="tests.community_app.rootconf",
            INSTALLED_APPS=[APP] + list(settings.INSTALLED_APPS),
        ):
            self.visit(client)

    def visit(self, client):
        assert reverse("community_app:hello") == "/community/hello/"
        page = client.get("/community/hello/")
        assert page.status_code == 200
        assert b"Hello from the community app." in page.content
        assert client.get("/community-plain/ping/").content == b"pong"
        # The core's own pages are still there behind them.
        assert client.get(reverse("index")).status_code == 200

    def test_the_apps_template_replaces_the_core_page(self, client):
        templates = copy.deepcopy(settings.TEMPLATES)
        templates[0]["DIRS"] = community.template_dirs([APP]) + list(
            templates[0]["DIRS"]
        )
        with override_settings(TEMPLATES=templates):
            page = client.get(reverse("index"))
        assert b"Community landing: this page replaces the core" in page.content
        page = client.get(reverse("index"))
        assert b"Community landing" not in page.content

    def test_the_apps_static_files_are_found_when_it_is_installed(self):
        with override_settings(INSTALLED_APPS=[APP] + list(settings.INSTALLED_APPS)):
            found = finders.find("community_app/hello.css")
        assert found == str(APP_DIR / "static" / "community_app" / "hello.css")

    def test_the_apps_stylesheet_replaces_the_cores(self):
        """The path the adapting guide gives for replacing the stylesheet."""
        core = finders.find("css/portal.css")
        assert core.endswith("portal/static/css/portal.css")
        with override_settings(INSTALLED_APPS=[APP] + list(settings.INSTALLED_APPS)):
            finders.get_finder.cache_clear()
            try:
                found = finders.find("css/portal.css")
            finally:
                finders.get_finder.cache_clear()
        assert found == str(APP_DIR / "static" / "css" / "portal.css")


def settings_in_a_fresh_interpreter(**env):
    """Import the settings in a new process with ``env`` and report the
    community-related values, or how the boot failed."""
    code = (
        "import json; from django.conf import settings as s;"
        "print(json.dumps({'EXTRA_APPS': s.EXTRA_APPS,"
        "'first_apps': s.INSTALLED_APPS[:2],"
        "'first_dir': str(s.TEMPLATES[0]['DIRS'][0])}))"
    )
    base = {
        "PATH": os.environ.get("PATH", ""),
        "DJANGO_SETTINGS_MODULE": "portal.settings",
        "SECRET_KEY": "s",
        "DEBUG": "1",
    }
    done = subprocess.run(
        [sys.executable, "-c", code],
        env={**base, **env},
        capture_output=True,
        text=True,
    )
    if done.returncode:
        return {"error": done.stderr.strip()}
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestAtBoot:
    def test_bare_by_default(self):
        found = settings_in_a_fresh_interpreter()
        assert found["EXTRA_APPS"] == []
        assert found["first_apps"][0] == "django.contrib.admin"
        assert found["first_dir"].endswith("/templates")

    def test_extra_apps_go_first_in_apps_and_templates(self):
        found = settings_in_a_fresh_interpreter(EXTRA_APPS=f"{APP},{PLAIN}")
        assert found["EXTRA_APPS"] == [APP, PLAIN]
        assert found["first_apps"] == [APP, PLAIN]
        assert found["first_dir"] == str(APP_DIR / "templates")

    def test_a_misspelled_app_fails_the_boot_by_name(self):
        found = settings_in_a_fresh_interpreter(EXTRA_APPS="flashlights_sumit")
        assert "EXTRA_APPS names 'flashlights_sumit'" in found["error"]
