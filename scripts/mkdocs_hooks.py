"""mkdocs hooks for the docs site (listed under ``hooks`` in mkdocs.yml).

mike builds each version into its own folder and sets ``site_url`` to that
folder without a trailing slash. The RSS plugin copies ``site_url`` into
its social-card integration while reading the config, and later pastes
image paths onto it as text, so the feed would point at
``.../0.1.0assets/...``. A hook runs after every plugin has read the
config, so the slash goes back there, and the copy the RSS plugin keeps is
brought in line at the next event, before any page is rendered.

The module imports nothing from mkdocs, so the test suite reads it inside
the image, where only the application's requirements are installed.
``mkdocs_priority`` is the attribute ``mkdocs.plugins.event_priority`` sets.
"""


def on_config(config):
    if config.site_url and not config.site_url.endswith("/"):
        config.site_url += "/"
    return config


on_config.mkdocs_priority = -100  # after every plugin has read the config


def on_files(files, config):
    cards = getattr(
        config.plugins.get("rss"), "integration_material_social_cards", None
    )
    if cards is not None and config.site_url:
        cards.mkdocs_site_url = config.site_url
    return files
