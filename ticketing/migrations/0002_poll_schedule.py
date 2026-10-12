# Polling is the baseline (decision 0012): every edition with a provider
# API, every 15 minutes. The schedule is data, editable under "Periodic
# tasks"; seeding it here gives a fresh database the same default. The
# speakers' nightly Pretix reconcile did the same for Pretix alone and is
# switched off rather than deleted, so turning it back on is one tick.

from django.db import migrations

TASK_NAME = "Poll ticketing registrations"
TASK_PATH = "ticketing.tasks.poll_registrations_task"
OLD_TASK_NAME = "Reconcile pretix orders for the speaker portal"


def seed(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    every, _ = IntervalSchedule.objects.get_or_create(every=15, period="minutes")
    PeriodicTask.objects.get_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK_PATH,
            "interval": every,
            "description": (
                "Fetch registrations changed since the last run, for every "
                "edition with a ticketing API; webhooks only make it faster."
            ),
        },
    )
    PeriodicTask.objects.filter(name=OLD_TASK_NAME).update(enabled=False)


def unseed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()
    PeriodicTask.objects.filter(name=OLD_TASK_NAME).update(enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ("ticketing", "0001_initial"),
        ("speakers", "0004_pretix_reminders_guide"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
