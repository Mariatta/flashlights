"""Fetch orders from pretix for every edition with a Pretix API set up (or
one edition), through its ticketing settings."""

from django.core.management.base import BaseCommand, CommandError

from portal.models import Conference
from speakers.pretix import reconcile
from ticketing.models import TicketingSettings


class Command(BaseCommand):
    help = "Fetch pretix orders and sync attendee demographics, per edition"

    def add_arguments(self, parser):
        parser.add_argument(
            "--conference", help="An edition's slug; every edition when left out."
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="Fetch every order, not only those changed since the last run.",
        )

    def handle(self, *args, **options):
        rows = TicketingSettings.objects.select_related("conference")
        if options["conference"]:
            if not Conference.objects.filter(slug=options["conference"]).exists():
                raise CommandError(f"No edition {options['conference']!r}.")
            rows = rows.filter(conference__slug=options["conference"])
        rows = [row for row in rows if row.has_api]
        if not rows:
            self.stdout.write("No edition has a Pretix API set up.")
            return
        for row in rows:
            if options["full"]:
                row.last_synced_at = None
                row.save(update_fields=["last_synced_at", "modified_date"])
            seen = reconcile(row.conference)
            self.stdout.write(
                self.style.SUCCESS(f"{row.conference}: {seen} order(s) synced")
            )
