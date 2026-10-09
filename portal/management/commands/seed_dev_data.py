"""One command for a usable local instance: ``manage.py seed_dev_data``.

Runs the two sample-data generators (volunteers, teams, sponsors; the
speaker program) on the active edition, gives the accounts a developer
will sign in as a known password, adds a few affiliations, and prints the
logins. Idempotent: run it again after a reset or to top up. DEBUG only,
like the generators it calls.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from affiliations.models import Affiliation, AffiliationKind

PASSWORD = "password123"

#: username -> role shown in the login table. Every account exists once
#: the generators ran; the speaker's is made by accepting her invitation.
LOGINS = [
    ("admin_user", "Organizer (superuser)"),
    ("organizer_lena", "Organizer (staff)"),
    ("volunteer1", "Volunteer, approved"),
    ("volunteer3", "Volunteer, pending review"),
    ("ada", "Speaker, onboarded"),
    ("sponsor_contact1", "Sponsor contact"),
]

AFFILIATIONS = {
    "admin_user": [
        (AffiliationKind.COMMUNITY, "Flashlights organisers", ""),
    ],
    "volunteer1": [
        (AffiliationKind.WORKPLACE, "Acme Analytics", "https://acme.example.org"),
        (AffiliationKind.PROJECT, "httpx", "https://github.com/encode/httpx"),
        (AffiliationKind.COMMUNITY, "Vancouver Python meetup", ""),
    ],
    "volunteer3": [
        (AffiliationKind.SCHOOL, "University of Example", ""),
    ],
    "ada": [
        (AffiliationKind.PROJECT, "Analytical Engine", ""),
        (AffiliationKind.COMMUNITY, "Vancouver Python meetup", ""),
    ],
}


class Command(BaseCommand):
    help = "Seed a local instance with sample accounts and data (DEBUG only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev_data only runs in development (DEBUG=True); it "
                "creates accounts with a known password."
            )
        call_command("generate_sample_data", stdout=self.stdout)
        call_command("generate_speaker_sample_data", stdout=self.stdout)
        self._speaker_login()
        self._affiliations()
        self.stdout.write(self.style.SUCCESS("\nSign in with (password: password123)"))
        for username, role in LOGINS:
            self.stdout.write(f"  {username:18} {role}")

    def _speaker_login(self):
        """The onboarded sample speaker's account is made by accepting the
        invitation (username ``ada``, from her email) with no password."""
        user = User.objects.get(username="ada")
        user.set_password(PASSWORD)
        user.save()

    def _affiliations(self):
        created = 0
        for username, rows in AFFILIATIONS.items():
            user = User.objects.get(username=username)
            for order, (kind, name, url) in enumerate(rows):
                _, was_created = Affiliation.objects.get_or_create(
                    user=user,
                    kind=kind,
                    name=name,
                    defaults={"url": url, "order": order},
                )
                created += was_created
        self.stdout.write(self.style.SUCCESS(f"Created {created} affiliations"))
