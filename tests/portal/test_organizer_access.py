"""What the second summit dry run found about running an edition without
being a superuser: who may delete and switch editions, rooms in the
portal, the proposal queue after the call closes, admin links, read-only
items for reviewers, and the Tickets pages on the Organize rail."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from portal.models import Conference
from speakers.checklists import add_adhoc_item
from speakers.constants import ItemOwner, ProposalDecision, SessionStatus
from speakers.models import Room
from tests.grants import on_team
from tests.speakers.factories import (
    add_presenter,
    make_presenter,
    make_proposal,
    make_session,
    make_settings,
)


def member(name, team="Organizers", lead=False):
    return on_team(
        User.objects.create_user(username=name, email=f"{name}@x.org"), team, lead=lead
    )


@pytest.mark.django_db
class TestEditions:
    def test_only_leads_delete(self, client, conference):
        past = Conference.objects.create(year=2019, name="Old", slug="old")
        client.force_login(member("ines"))
        listing = client.get(reverse("conference_list")).content.decode()
        assert reverse("conference_delete", args=[past.pk]) not in listing
        assert (
            client.post(reverse("conference_delete", args=[past.pk])).status_code == 403
        )
        assert Conference.objects.filter(pk=past.pk).exists()
        client.force_login(member("mara", lead=True))
        client.post(reverse("conference_delete", args=[past.pk]))
        assert not Conference.objects.filter(pk=past.pk).exists()

    def test_only_leads_switch_the_active_edition(self, client, conference):
        past = Conference.objects.create(year=2024, name="Past", slug="past")
        client.force_login(member("ines"))
        page = client.get(reverse("conference_edit", args=[past.pk]))
        assert page.context["form"].fields["is_active"].disabled
        client.post(
            reverse("conference_edit", args=[past.pk]),
            {
                "year": 2024,
                "name": "Past",
                "slug": "past",
                "cadence": "ONCE",
                "conference_date": "2027-05-01",
                "is_active": "on",
                "sponsorship_goal": "0",
                "donation_goal": "0",
                "proposals_count": "0",
                "chat_platform": "NONE",
            },
        )
        assert Conference.get_active() == conference


@pytest.mark.django_db
class TestRooms:
    def test_organizers_add_and_edit_rooms(self, client, conference):
        make_settings(conference)
        client.force_login(member("ines"))
        assert client.get(reverse("speakers:room_list")).status_code == 200
        client.post(
            reverse("speakers:room_create"),
            {"name": "Room 201A", "kind": "ROOM", "url": "", "is_active": "on"},
        )
        room = Room.objects.get(name="Room 201A")
        duplicate = client.post(
            reverse("speakers:room_create"),
            {"name": "room 201a", "kind": "ROOM", "url": "", "is_active": "on"},
        )
        assert "already has an online room" in duplicate.content.decode()
        client.post(
            reverse("speakers:room_edit", args=[room.pk]),
            {"name": "Room 201B", "kind": "ROOM", "url": ""},
        )
        room.refresh_from_db()
        assert room.name == "Room 201B" and not room.is_active
        assert "Room 201B" in client.get(reverse("speakers:room_list")).content.decode()

    def test_discord_only_on_a_discord_edition(self, client, conference):
        make_settings(conference)
        client.force_login(member("ines"))
        form = client.get(reverse("speakers:room_create")).context["form"]
        assert "discord_id" in form.fields
        conference.chat_platform = "NONE"
        conference.save()
        form = client.get(reverse("speakers:room_create")).context["form"]
        assert "discord_id" not in form.fields

    def test_in_person_rooms_default_to_a_room(self, client, conference):
        make_settings(conference, event_format="IN_PERSON")
        client.force_login(member("ines"))
        form = client.get(reverse("speakers:room_create")).context["form"]
        assert form.fields["kind"].initial == "ROOM"

    def test_reviewers_do_not_manage_rooms(self, client, conference):
        make_settings(conference)
        client.force_login(member("rae", "Proposal reviewers"))
        assert client.get(reverse("speakers:room_list")).status_code == 403


@pytest.mark.django_db
class TestProposalsAfterTheCall:
    def test_the_rail_keeps_the_queue_while_proposals_wait(self, client, conference):
        make_settings(conference, proposals_open=False)
        session = make_session(conference, status=SessionStatus.PROPOSED)
        presenter = make_presenter(conference)
        add_presenter(session, presenter)
        proposal = make_proposal(session, presenter)
        client.force_login(member("rae", "Proposal reviewers"))
        queue_url = reverse("speakers:proposal_queue")
        page = client.get(reverse("speakers:session_list")).content.decode()
        assert queue_url in page
        proposal.decision = ProposalDecision.APPROVED
        proposal.save()
        page = client.get(reverse("speakers:session_list")).content.decode()
        assert queue_url not in page


@pytest.mark.django_db
class TestAdminLinks:
    def test_only_a_staff_superuser_is_offered_the_admin(
        self, client, conference, admin_user
    ):
        staff = member("ines")
        staff.is_staff = True
        staff.save()
        client.force_login(staff)
        page = client.get(reverse("organizer_dashboard")).content.decode()
        assert reverse("admin:index") not in page
        client.force_login(admin_user)
        page = client.get(reverse("organizer_dashboard")).content.decode()
        assert reverse("admin:index") in page


@pytest.mark.django_db
class TestDashboardCards:
    def test_the_top_line_cards_carry_the_stat_card_class(
        self, client, conference, admin_user
    ):
        """A stray quote once made stat-card an attribute, and the cards
        lost their styling with every test still passing."""
        client.force_login(admin_user)
        page = client.get(reverse("organizer_dashboard")).content.decode()
        # Onboarded, sponsorship and donations; tickets only with Pretix.
        assert page.count('class="card h-100 stat-card"') == 3
        assert '" stat-card' not in page


@pytest.mark.django_db
class TestReviewersReadItems:
    def test_a_reviewer_reads_without_ticking(self, client, conference):
        make_settings(conference)
        session = make_session(conference)
        item = add_adhoc_item(
            conference, "Book the room", ItemOwner.ORGANIZER, session=session
        )
        client.force_login(member("rae", "Proposal reviewers"))
        page = client.get(session.get_absolute_url()).content.decode()
        assert reverse("speakers:item_status", args=[item.pk]) not in page
        detail = client.get(reverse("speakers:item_detail", args=[item.pk]))
        assert detail.status_code == 200
        assert "You can read this item" in detail.content.decode()
        status = client.post(
            reverse("speakers:item_status", args=[item.pk]), {"status": "DONE"}
        )
        assert status.status_code == 403
        client.force_login(member("ines"))
        page = client.get(session.get_absolute_url()).content.decode()
        assert reverse("speakers:item_status", args=[item.pk]) in page


@pytest.mark.django_db
class TestTicketsOnTheRail:
    def test_the_pages_carry_the_rail_and_saving_stays_there(self, client, conference):
        client.force_login(member("ines"))
        tickets = reverse("conference_tickets", args=[conference.pk])
        page = client.get(tickets).content.decode()
        assert "Import registrations" in page and f'href="{tickets}"' in page
        response = client.post(
            tickets,
            {
                "provider": "CSV",
                "base_url": "https://pretix.eu/api/v1/",
                "csv_lines": "email = Email",
            },
        )
        assert response.status_code == 302 and response.url == tickets
