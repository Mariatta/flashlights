"""Import a CSV export of an edition's registrations."""

from django.core.management.base import BaseCommand, CommandError

from portal.models import Conference
from ticketing.models import ticketing_for
from ticketing.sync import CsvImportError, import_csv


class Command(BaseCommand):
    help = "Import a CSV export of registrations into an edition"

    def add_arguments(self, parser):
        parser.add_argument("conference", help="The edition's slug.")
        parser.add_argument("path", help="The CSV file.")

    def handle(self, *args, conference, path, **options):
        edition = Conference.objects.filter(slug=conference).first()
        if edition is None:
            raise CommandError(f"No edition {conference!r}.")
        row = ticketing_for(edition)
        if row is None:
            raise CommandError("Set up the edition's Tickets page first.")
        with open(path, "rb") as handle:
            content = handle.read()
        try:
            result = import_csv(row, content)
        except CsvImportError as exc:
            raise CommandError(str(exc)) from exc
        for line, reason in result.skipped:
            self.stdout.write(f"Line {line} skipped: {reason}")
        self.stdout.write(
            self.style.SUCCESS(
                f"{result.imported} row(s) imported, {result.registered} registered"
            )
        )
