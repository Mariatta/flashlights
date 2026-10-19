"""mkdocs hooks for the docs site (listed under ``hooks`` in mkdocs.yml).

mike builds each version into its own folder and sets ``site_url`` to that
folder without a trailing slash. The RSS plugin copies ``site_url`` into
its social-card integration while reading the config, and later pastes
image paths onto it as text, so the feed would point at
``.../0.1.0assets/...``. A hook runs after every plugin has read the
config, so the slash goes back there, and the copy the RSS plugin keeps is
brought in line at the next event, before any page is rendered.
"""

from mkdocs.plugins import event_priority


@event_priority(-100)
def on_config(config):
    if config.site_url and not config.site_url.endswith("/"):
        config.site_url += "/"
    return config


def on_files(files, config):
    cards = getattr(
        config.plugins.get("rss"), "integration_material_social_cards", None
    )
    if cards is not None and config.site_url:
        cards.mkdocs_site_url = config.site_url
    return files
