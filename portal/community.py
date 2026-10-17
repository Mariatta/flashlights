"""Community apps: Django apps a deployment adds to the core.

The core is one image. A community whose needs configuration cannot meet
ships a Django app in its own repository, builds its image from the core's
and names the app in ``EXTRA_APPS``. The core then installs the app ahead
of its own apps, searches the app's ``templates/`` folder before its own,
serves the app's ``static/`` files, and includes the app's ``urls`` module
under a prefix. With the variable empty the core runs bare, so one image
serves both kinds of deployment.

What this module reads from an app is part of the contract a community
app relies on; the whole contract is written down in
docs/developer/community_apps.md.
"""

import importlib
import importlib.util
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.urls import include, path


def names(env):
    """The apps named in ``EXTRA_APPS``: comma-separated module paths."""
    return [
        name.strip() for name in env.get("EXTRA_APPS", "").split(",") if name.strip()
    ]


def package_dir(name):
    """The directory of the app's package.

    Raises ``ImproperlyConfigured`` naming the app when it cannot be
    imported, so a misspelled ``EXTRA_APPS`` fails the boot with the
    variable's name rather than deep inside Django's app loading.
    """
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:
        spec = None
    if spec is None or not spec.submodule_search_locations:
        raise ImproperlyConfigured(
            f"EXTRA_APPS names {name!r}, which is not an importable package. "
            "Each entry is the dotted path of a Django app the image installs."
        )
    return Path(list(spec.submodule_search_locations)[0])


def template_dirs(apps):
    """Each app's ``templates/`` folder, for the front of the template search.

    Django looks in the project's template directories before any app's,
    and the core keeps most of its templates in the project-level
    ``templates/`` folder; putting an app's folder ahead of it is what lets
    the app replace a core template by path.
    """
    dirs = []
    for name in apps:
        folder = package_dir(name) / "templates"
        if folder.is_dir():
            dirs.append(folder)
    return dirs


def url_prefix(name, module):
    """Where an app's URLs are included.

    The app's ``urls`` module may set ``prefix`` (``"summit/"``); otherwise
    the last part of the app's module path, with hyphens for underscores.
    """
    prefix = getattr(module, "prefix", None)
    if prefix is None:
        prefix = name.rsplit(".", 1)[-1].replace("_", "-") + "/"
    prefix = prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return prefix


def urlpatterns(apps):
    """One ``path(prefix, include(app.urls))`` per app that has a ``urls`` module.

    The module's ``app_name`` becomes the namespace, as for any include.
    """
    patterns = []
    for name in apps:
        try:
            spec = importlib.util.find_spec(f"{name}.urls")
        except ModuleNotFoundError:
            spec = None
        if spec is None:
            continue
        module = importlib.import_module(f"{name}.urls")
        patterns.append(path(url_prefix(name, module), include(module)))
    return patterns
