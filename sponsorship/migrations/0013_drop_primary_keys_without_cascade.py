"""The 0003 migration, written for a database that drops no column with CASCADE.

Upstream's 0003 swaps the primary key of SponsorshipProfile and
SponsorshipTier for a link to BaseModel by dropping the ``id`` column while
``additional_contacts`` (a many-to-many table) and ``sponsorship_tier`` (a
foreign key) still point at it. Django 5.2 dropped columns with CASCADE, so
Postgres took the dependent constraints with the column; Django 6.0 no
longer does, and a fresh database stops at 0003 with "cannot drop column id
... because other objects depend on it".

This migration replaces 0003 on a database that has not applied it: the
two relations are removed first and put back after the new primary keys
exist, with the definitions they had at that point, so the resulting state
is the one 0003 leaves. A database that has already applied 0003 records
this migration as applied and runs nothing. Upstream's file is untouched.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [
        ("sponsorship", "0003_remove_sponsorshipprofile_application_status_and_more"),
    ]

    dependencies = [
        ("portal", "0002_alter_basemodel_creation_date_and_more"),
        ("sponsorship", "0002_sponsorshiptier_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="sponsorshipprofile",
            name="application_status",
        ),
        migrations.RemoveField(
            model_name="sponsorshipprofile",
            name="additional_contacts",
        ),
        migrations.RemoveField(
            model_name="sponsorshipprofile",
            name="sponsorship_tier",
        ),
        migrations.RemoveField(
            model_name="sponsorshipprofile",
            name="id",
        ),
        migrations.RemoveField(
            model_name="sponsorshiptier",
            name="id",
        ),
        migrations.AddField(
            model_name="sponsorshipprofile",
            name="basemodel_ptr",
            field=models.OneToOneField(
                auto_created=True,
                on_delete=django.db.models.deletion.CASCADE,
                parent_link=True,
                primary_key=True,
                serialize=False,
                to="portal.basemodel",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sponsorshipprofile",
            name="progress_status",
            field=models.IntegerField(
                choices=[
                    (1, "Not Contacted"),
                    (2, "Awaiting Response"),
                    (3, "Rejected"),
                    (4, "Accepted"),
                    (5, "Approved"),
                    (6, "Agreement Sent"),
                    (7, "Agreement Signed"),
                    (8, "Invoiced"),
                    (9, "Paid"),
                    (10, "Cancelled"),
                ],
                default=1,
            ),
        ),
        migrations.AddField(
            model_name="sponsorshiptier",
            name="basemodel_ptr",
            field=models.OneToOneField(
                auto_created=True,
                on_delete=django.db.models.deletion.CASCADE,
                parent_link=True,
                primary_key=True,
                serialize=False,
                to="portal.basemodel",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sponsorshipprofile",
            name="sponsorship_tier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="sponsorship.sponsorshiptier",
            ),
        ),
        migrations.AddField(
            model_name="sponsorshipprofile",
            name="additional_contacts",
            field=models.ManyToManyField(
                blank=True,
                related_name="additional_contacts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
