"""A person's handles kept once on the account (``portal_account.handles``),
filled from the volunteer and presenter rows they already typed them into.

The newest volunteer profile is read first (it was the canonical copy of
the Discord username), then the newest presenter; blanks come from older
rows.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

VOLUNTEER_COLUMNS = {
    "github": "github_username",
    "discord": "discord_username",
    "instagram": "instagram_username",
    "bluesky": "bluesky_username",
    "mastodon": "mastodon_url",
    "x": "x_username",
    "linkedin": "linkedin_url",
}
PRESENTER_COLUMNS = {
    "website": "website_url",
    "github": "github_username",
    "mastodon": "mastodon_url",
    "linkedin": "linkedin_url",
    "bluesky": "bluesky_username",
    "discord": "discord_username",
}


def fill_from_roles(apps, schema_editor):
    Handle = apps.get_model("portal_account", "Handle")
    VolunteerProfile = apps.get_model("volunteer", "VolunteerProfile")
    Presenter = apps.get_model("speakers", "Presenter")
    found = {}
    rows = [
        (row, VOLUNTEER_COLUMNS)
        for row in VolunteerProfile.objects.exclude(user=None).order_by(
            "-conference__year", "-id"
        )
    ] + [
        (row, PRESENTER_COLUMNS)
        for row in Presenter.objects.exclude(user=None).order_by(
            "-conference__year", "-id"
        )
    ]
    for row, columns in rows:
        person = found.setdefault(row.user_id, {})
        for code, column in columns.items():
            value = (getattr(row, column) or "").strip()
            if value and not person.get(code):
                person[code] = value[:200]
    Handle.objects.bulk_create(
        Handle(user_id=user_id, channel=code, value=value)
        for user_id, handles in found.items()
        for code, value in handles.items()
    )


class Migration(migrations.Migration):

    dependencies = [
        ("portal_account", "0004_maintenance_setup"),
        ("volunteer", "0016_flashlights_rebrand"),
        ("speakers", "0022_flashlights"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Handle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("creation_date", models.DateTimeField(auto_now_add=True)),
                ("modified_date", models.DateTimeField(auto_now=True)),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("website", "Website"),
                            ("github", "GitHub username"),
                            ("discord", "Discord username"),
                            ("mastodon", "Mastodon"),
                            ("bluesky", "Bluesky username"),
                            ("linkedin", "LinkedIn"),
                            ("instagram", "Instagram username"),
                            ("x", "X username"),
                        ],
                        max_length=20,
                    ),
                ),
                ("value", models.CharField(max_length=200)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="handles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["user_id", "channel"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "channel"),
                        name="portal_account_handle_per_channel",
                    )
                ],
            },
        ),
        migrations.RunPython(fill_from_roles, migrations.RunPython.noop),
    ]
