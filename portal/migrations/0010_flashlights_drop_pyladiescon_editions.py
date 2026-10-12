# Upstream's 0005_backfill_conferences seeds every fresh database with the
# PyLadiesCon 2023 to 2026 editions (and PyLadiesCon's historical numbers),
# so a new Flashlights instance started with four editions of someone
# else's event. Upstream migrations are not edited (decision 0001); this
# one removes those rows instead, but only while nothing hangs off them: an
# edition anything points at is left alone.

from django.db import migrations

BACKFILLED = {year: f"PyLadiesCon {year}" for year in (2023, 2024, 2025, 2026)}


def drop_untouched(apps, schema_editor):
    Conference = apps.get_model("portal", "Conference")
    relations = [
        rel
        for rel in Conference._meta.related_objects
        if rel.related_model is not None and not rel.parent_link
    ]
    for year, name in BACKFILLED.items():
        edition = Conference.objects.filter(year=year, name=name).first()
        if edition is None:
            continue
        used = any(
            rel.related_model._default_manager.filter(
                **{rel.field.name: edition}
            ).exists()
            for rel in relations
            if rel.field.name and not rel.many_to_many
        )
        if not used:
            edition.delete()


class Migration(migrations.Migration):

    dependencies = [("portal", "0009_flashlights_venue_and_chat")]

    operations = [migrations.RunPython(drop_untouched, migrations.RunPython.noop)]
