"""
Management command to generate sample data for local development.

This command creates sample data for testing and development purposes:
- Users with various roles (admin, volunteer, staff, superuser)
- Teams (the Organizers team grants organizer access)
- Volunteer Profiles in various states
- Sponsorship Tiers and Profiles
- Individual Donations

This command ONLY runs in development mode (DEBUG=True) and will refuse
to run in production environments.
"""

import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db.models.signals import post_save
from django.utils import timezone

from portal.models import Conference
from portal_account.models import PortalProfile
from sponsorship.models import (
    IndividualDonation,
    SponsorshipProfile,
    SponsorshipProgressStatus,
    SponsorshipTier,
)
from sponsorship.signals import sponsorship_profile_signal
from volunteer.constants import ApplicationStatus, Region
from volunteer.models import (
    Team,
    VolunteerProfile,
    volunteer_profile_signal,
)
from volunteer.permission_presets import ORGANIZERS, PRESETS, permissions_for


class Command(BaseCommand):
    help = "Generate sample data for local development environment"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing sample data before generating new data",
        )

    def handle(self, *args, **options):
        # Safety check: only run in DEBUG mode
        if not settings.DEBUG:
            raise CommandError(
                "This command can only be run in development mode (DEBUG=True). "
                "It is not safe to run in production."
            )

        self.stdout.write(
            self.style.WARNING(
                "Starting sample data generation for local development..."
            )
        )

        # Generate data
        self._generate_conference()
        self._generate_users()
        self._generate_teams()
        self._grant_organizers()
        self._generate_volunteer_profiles()
        self._generate_sponsorship_tiers()
        self._generate_sponsorship_profiles()
        self._generate_donations()

        self.stdout.write(
            self.style.SUCCESS("Sample data generation completed successfully!")
        )

    def _generate_conference(self):
        """Generate the active conference every other record is scoped to."""
        self.stdout.write("Generating event...")

        self.conference, created = Conference.objects.get_or_create(
            year=2025,
            defaults={
                "name": "Flashlights 2025",
                "slug": "2025",
                "is_active": True,
                "volunteer_application_open": True,
                "pretix_event_slug": "2025",
            },
        )
        verb = "Created" if created else "Using existing"
        self.stdout.write(self.style.SUCCESS(f"  ✓ {verb} event: {self.conference}\n"))

    def _generate_users(self):
        """Generate sample users: two organizer accounts and the volunteers."""
        self.stdout.write("Generating users...")

        users_data = [
            {
                "username": "admin_user",
                "email": "admin@example.com",
                "first_name": "Admin",
                "last_name": "User",
                "is_staff": True,
                "is_superuser": True,
            },
            {
                "username": "staff_user",
                "email": "staff@example.com",
                "first_name": "Staff",
                "last_name": "Member",
                "is_staff": True,
                "is_superuser": False,
            },
            {
                "username": "volunteer1",
                "email": "volunteer1@example.com",
                "first_name": "Alice",
                "last_name": "Volunteer",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "volunteer2",
                "email": "volunteer2@example.com",
                "first_name": "Bob",
                "last_name": "Helper",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "volunteer3",
                "email": "volunteer3@example.com",
                "first_name": "Carol",
                "last_name": "Smith",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "volunteer4",
                "email": "volunteer4@example.com",
                "first_name": "Diana",
                "last_name": "Jones",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "volunteer5",
                "email": "volunteer5@example.com",
                "first_name": "Eve",
                "last_name": "Brown",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "sponsor_contact1",
                "email": "sponsor1@techcorp.com",
                "first_name": "John",
                "last_name": "Sponsor",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "sponsor_contact2",
                "email": "sponsor2@innovate.com",
                "first_name": "Jane",
                "last_name": "Corporate",
                "is_staff": False,
                "is_superuser": False,
            },
        ]

        created_count = 0
        for user_data in users_data:
            user, created = User.objects.get_or_create(
                username=user_data["username"],
                defaults={
                    "email": user_data["email"],
                    "first_name": user_data["first_name"],
                    "last_name": user_data["last_name"],
                    "is_staff": user_data["is_staff"],
                    "is_superuser": user_data["is_superuser"],
                },
            )
            if created:
                # Set a default password for all sample users: "password123"
                user.set_password("password123")
                user.save()
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Created user: {user.username}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  ~ User already exists: {user.username}")
                )
            portal_profile, _ = PortalProfile.objects.get_or_create(user=user)
            portal_profile.tos_agreement = True
            portal_profile.coc_agreement = True
            portal_profile.save()

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} new users\n"))

    def _grant_organizers(self):
        """The Organizers team for the edition, from the §7.1 preset, with the
        admin and staff sample accounts on it: access comes from the team,
        not from the Django flags (design §7.1)."""
        self.stdout.write("Granting through the Organizers team...")
        team, created = Team.objects.get_or_create(
            conference=self.conference,
            short_name=ORGANIZERS,
            defaults={
                "description": "The core team: runs the edition end to end.",
                "open_to_new_members": False,
            },
        )
        if created:
            team.permissions.set(permissions_for(PRESETS[ORGANIZERS].members))
            team.lead_permissions.set(permissions_for(PRESETS[ORGANIZERS].leads))
        # Both accounts exist by now: _generate_users runs first.
        for username in ("admin_user", "staff_user"):
            user = User.objects.get(username=username)
            profile, _ = VolunteerProfile.objects.get_or_create(
                user=user,
                conference=self.conference,
                defaults={
                    "application_status": ApplicationStatus.APPROVED,
                    "discord_username": username,
                },
            )
            profile.teams.add(team)
            if user.is_superuser:
                team.team_leads.add(profile)
        self.stdout.write(
            self.style.SUCCESS(f"  ✓ Organizers team ready ({team.conference.year})\n")
        )

    def _generate_teams(self):
        """Generate sample volunteer teams."""
        self.stdout.write("Generating volunteer teams...")

        teams_data = [
            {
                "short_name": "Website Team",
                "description": "Responsible for developing and maintaining the event website",
                "open_to_new_members": True,
            },
            {
                "short_name": "Social Media Team",
                "description": "Manages social media presence and content creation",
                "open_to_new_members": True,
            },
            {
                "short_name": "Content Team",
                "description": "Creates blog posts, documentation, and other written content",
                "open_to_new_members": True,
            },
            {
                "short_name": "Design Team",
                "description": "Creates visual assets and designs for the event",
                "open_to_new_members": True,
            },
            {
                "short_name": "Program Committee",
                "description": "Reviews and selects talks and proposals for the event",
                "open_to_new_members": False,
            },
            {
                "short_name": "Sponsorship Team",
                "description": "Manages sponsor relationships and benefits",
                "open_to_new_members": False,
            },
        ]

        created_count = 0
        for team_data in teams_data:
            team, created = Team.objects.get_or_create(
                short_name=team_data["short_name"],
                defaults={
                    "conference": self.conference,
                    "description": team_data["description"],
                    "open_to_new_members": team_data["open_to_new_members"],
                },
            )
            if created:
                created_count += 1
                status = "open" if team.open_to_new_members else "closed"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Created team: {team.short_name} ({status})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  ~ Team already exists: {team.short_name}")
                )

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} new teams\n"))

    def _generate_volunteer_profiles(self):
        """Generate sample volunteer profiles with various statuses."""
        self.stdout.write("Generating volunteer profiles...")

        # Temporarily disable the post_save signal to avoid sending emails during data generation
        post_save.disconnect(volunteer_profile_signal, sender=VolunteerProfile)

        try:
            self._create_volunteer_profiles()
        finally:
            # Re-enable the signal
            post_save.connect(volunteer_profile_signal, sender=VolunteerProfile)

    def _create_volunteer_profiles(self):
        """Create the actual volunteer profiles."""
        # Get the volunteers (non-staff users)
        volunteers = User.objects.filter(username__startswith="volunteer")
        teams = list(Team.objects.all())

        if not volunteers.exists():
            self.stdout.write(
                self.style.WARNING(
                    "  ! No volunteer users found. Skipping profile generation.\n"
                )
            )
            return

        profiles_data = [
            {
                "user": volunteers[0],  # volunteer1
                "status": ApplicationStatus.APPROVED,
                "discord_username": "alice_vol",
                "github_username": "alice-volunteer",
                "region": Region.NORTH_AMERICA,
                "availability_hours_per_week": 10,
                "teams": (
                    teams[:2] if len(teams) >= 2 else teams
                ),  # Website & Social Media
            },
            {
                "user": volunteers[1],  # volunteer2
                "status": ApplicationStatus.APPROVED,
                "discord_username": "bob_helper",
                "instagram_username": "bob_helper",
                "region": Region.EUROPE,
                "availability_hours_per_week": 5,
                "teams": (
                    teams[1:3] if len(teams) >= 3 else teams
                ),  # Social Media & Content
            },
            {
                "user": volunteers[2],  # volunteer3
                "status": ApplicationStatus.PENDING,
                "discord_username": "carol_smith",
                "github_username": "carol-codes",
                "region": Region.ASIA,
                "availability_hours_per_week": 8,
                "teams": [],  # No team assignment yet (pending)
            },
            {
                "user": volunteers[3],  # volunteer4
                "status": ApplicationStatus.WAITLISTED,
                "discord_username": "diana_jones",
                "bluesky_username": "diana.bsky.social",
                "region": Region.SOUTH_AMERICA,
                "availability_hours_per_week": 3,
                "teams": [],  # No team assignment (waitlisted)
            },
            {
                "user": volunteers[4],  # volunteer5
                "status": ApplicationStatus.REJECTED,
                "discord_username": "eve_brown",
                "x_username": "eve_brown",
                "region": Region.AFRICA,
                "availability_hours_per_week": 2,
                "teams": [],  # No team assignment (rejected)
            },
        ]

        created_count = 0
        for profile_data in profiles_data:
            profile, created = VolunteerProfile.objects.get_or_create(
                user=profile_data["user"],
                conference=self.conference,
                defaults={
                    "application_status": profile_data["status"],
                    "discord_username": profile_data["discord_username"],
                    "github_username": profile_data.get("github_username", ""),
                    "instagram_username": profile_data.get("instagram_username", ""),
                    "bluesky_username": profile_data.get("bluesky_username", ""),
                    "x_username": profile_data.get("x_username", ""),
                    "region": profile_data["region"],
                    "availability_hours_per_week": profile_data[
                        "availability_hours_per_week"
                    ],
                },
            )

            if created:
                # Add many-to-many relationships
                if profile_data["teams"]:
                    profile.teams.set(profile_data["teams"])

                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Created profile for {profile.user.username} ({profile.application_status})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ~ Profile already exists for {profile.user.username}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new volunteer profiles\n")
        )

    def _generate_sponsorship_tiers(self):
        """Generate sample sponsorship tiers."""
        self.stdout.write("Generating sponsorship tiers...")

        tiers_data = [
            {
                "name": "Championship",
                "amount": 25000.00,
                "description": "Premier sponsorship tier with maximum visibility and benefits",
            },
            {
                "name": "Elite",
                "amount": 15000.00,
                "description": "High-level sponsorship with prominent branding opportunities",
            },
            {
                "name": "Supporter",
                "amount": 10000.00,
                "description": "Strong support tier with significant event presence",
            },
            {
                "name": "Contributor",
                "amount": 5000.00,
                "description": "Mid-level sponsorship with good visibility",
            },
            {
                "name": "Community",
                "amount": 2500.00,
                "description": "Entry-level sponsorship for community supporters",
            },
        ]

        created_count = 0
        for tier_data in tiers_data:
            tier, created = SponsorshipTier.objects.get_or_create(
                name=tier_data["name"],
                conference=self.conference,
                defaults={
                    "amount": tier_data["amount"],
                    "description": tier_data["description"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Created tier: {tier.name} (${tier.amount})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  ~ Tier already exists: {tier.name}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new sponsorship tiers\n")
        )

    def _generate_sponsorship_profiles(self):
        """Generate sample sponsorship profiles."""
        self.stdout.write("Generating sponsorship profiles...")

        # Temporarily disable the post_save signal to avoid sending emails during data generation
        post_save.disconnect(sponsorship_profile_signal, sender=SponsorshipProfile)

        try:
            self._create_sponsorship_profiles()
        finally:
            # Re-enable the signal
            post_save.connect(sponsorship_profile_signal, sender=SponsorshipProfile)

    def _create_sponsorship_profiles(self):
        """Create the actual sponsorship profiles."""
        # Get sponsor contact users
        sponsor_users = User.objects.filter(username__startswith="sponsor_contact")

        # Get sponsorship tiers
        tiers = list(SponsorshipTier.objects.all())

        if not sponsor_users.exists():
            self.stdout.write(
                self.style.WARNING(
                    "  ! No sponsor contact users found. Skipping sponsorship profile generation.\n"
                )
            )
            return

        if not tiers:
            self.stdout.write(
                self.style.WARNING(
                    "  ! No sponsorship tiers found. Skipping sponsorship profile generation.\n"
                )
            )
            return

        profiles_data = [
            {
                "organization_name": "TechCorp International",
                "main_contact_user": sponsor_users[0],
                "tier": tiers[0] if len(tiers) > 0 else None,  # Championship
                "progress_status": SponsorshipProgressStatus.PAID,
                "sponsor_contact_name": "John Sponsor",
                "sponsors_contact_email": "sponsor1@techcorp.com",
                "company_description": "Leading technology company specializing in cloud services and AI",
                "organization_address": "123 Tech Street, San Francisco, CA 94105, USA",
            },
            {
                "organization_name": "Innovate Solutions LLC",
                "main_contact_user": (
                    sponsor_users[1] if len(sponsor_users) > 1 else sponsor_users[0]
                ),
                "tier": tiers[2] if len(tiers) > 2 else tiers[0],  # Supporter
                "progress_status": SponsorshipProgressStatus.INVOICED,
                "sponsor_contact_name": "Jane Corporate",
                "sponsors_contact_email": "sponsor2@innovate.com",
                "company_description": "Innovative software solutions for modern businesses",
                "organization_address": "456 Innovation Ave, Austin, TX 78701, USA",
            },
            {
                "organization_name": "DataWorks Inc",
                "main_contact_user": sponsor_users[0],
                "tier": tiers[1] if len(tiers) > 1 else None,  # Elite
                "progress_status": SponsorshipProgressStatus.AGREEMENT_SIGNED,
                "sponsor_contact_name": "Bob DataExpert",
                "sponsors_contact_email": "bob@dataworks.com",
                "company_description": "Data analytics and business intelligence platform",
                "organization_address": "789 Data Blvd, Seattle, WA 98101, USA",
            },
            {
                "organization_name": "PyTools Foundation",
                "main_contact_user": (
                    sponsor_users[1] if len(sponsor_users) > 1 else sponsor_users[0]
                ),
                "tier": tiers[3] if len(tiers) > 3 else None,  # Contributor
                "progress_status": SponsorshipProgressStatus.APPROVED,
                "sponsor_contact_name": "Alice Pythonista",
                "sponsors_contact_email": "alice@pytools.org",
                "company_description": "Non-profit organization supporting Python development tools",
                "organization_address": "321 Python Way, Portland, OR 97201, USA",
            },
            {
                "organization_name": "CloudNative Systems",
                "main_contact_user": sponsor_users[0],
                "tier": tiers[4] if len(tiers) > 4 else None,  # Community
                "progress_status": SponsorshipProgressStatus.AWAITING_RESPONSE,
                "sponsor_contact_name": "Chris Clouder",
                "sponsors_contact_email": "chris@cloudnative.io",
                "company_description": "Cloud-native infrastructure and DevOps solutions",
                "organization_address": "555 Cloud Lane, Denver, CO 80202, USA",
            },
        ]

        created_count = 0
        for profile_data in profiles_data:
            profile, created = SponsorshipProfile.objects.get_or_create(
                organization_name=profile_data["organization_name"],
                defaults={
                    "conference": self.conference,
                    "main_contact_user": profile_data["main_contact_user"],
                    "sponsorship_tier": profile_data["tier"],
                    "progress_status": profile_data["progress_status"],
                    "sponsor_contact_name": profile_data["sponsor_contact_name"],
                    "sponsors_contact_email": profile_data["sponsors_contact_email"],
                    "company_description": profile_data["company_description"],
                    "organization_address": profile_data["organization_address"],
                },
            )
            if created:
                created_count += 1
                status_label = SponsorshipProgressStatus(profile.progress_status).label
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Created sponsorship: {profile.organization_name} ({status_label})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ~ Sponsorship already exists: {profile.organization_name}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new sponsorship profiles\n")
        )

    def _generate_donations(self):
        """Generate sample individual donations."""
        self.stdout.write("Generating individual donations...")

        created_count = 0
        for i in range(5):
            donation, created = IndividualDonation.objects.get_or_create(
                transaction_id=f"transaction-{i+1}",
                defaults={
                    "conference": self.conference,
                    "donor_name": f"Donor {i+1}",
                    "donor_email": f"donor{i+1}@example.com",
                    "donation_amount": random.randint(5, 300),
                    "transaction_date": timezone.now()
                    - timedelta(days=random.randint(1, 30)),
                },
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Created donation: {donation.donor_name} (${donation.donation_amount})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ~ Donation already exists: {donation.donor_name}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} new individual donations\n")
        )
