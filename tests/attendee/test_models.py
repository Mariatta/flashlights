from decimal import Decimal

import pytest

from attendee.models import AttendeeProfile, PretixOrder
from tests.ticketing_ids import (
    AGE_RANGE,
    CITY,
    COUNTRY,
    CURRENT_POSITION,
    EXPECTATION,
    EXPERIENCE_LEVEL,
    HEARD_ABOUT,
    MAY_SHARE_EMAIL,
    ORGANIZATION,
    PARTICIPATED_BEFORE,
    STAY_ANONYMOUS,
    make_ticketing,
)
from ticketing.adapters.pretix import PretixAdapter


def normalised(ticketing, data):
    """Pretix's order as the registration the models record."""
    return PretixAdapter(ticketing).normalise(data)


def answers(*pairs):
    """``(question, answer)`` pairs as normalised answers."""
    return [{"question": q, "answer": a, "options": []} for q, a in pairs]


FULL_ANSWERS = answers(
    (CITY, "Vancouver"),
    (COUNTRY, "United States"),
    (EXPECTATION, "Networking, Learn new things, Support community activities"),
    (HEARD_ABOUT, "Social Media, Other"),
    (PARTICIPATED_BEFORE, "No, this is my first one"),
    (AGE_RANGE, "19-25"),
    (ORGANIZATION, "Umbrella Corp"),
    (CURRENT_POSITION, "Student/Intern, Other"),
    (EXPERIENCE_LEVEL, "Junior"),
    (MAY_SHARE_EMAIL, "Yes, I'm interested"),
)


@pytest.fixture(autouse=True)
def mapped(conference):
    """The edition's questions mapped: the attendee app
    no longer carries anyone's question ids."""
    return make_ticketing(conference)


@pytest.mark.django_db
class TestPretixOrderModel:

    def test_pretix_order_str_representation(self):
        """Test string representation of PretixOrder."""
        order = PretixOrder(order_code="ORDER123")
        assert str(order) == order.order_code

    def test_anonymous_from_answers(self, pretix_order_data, conference, mapped):
        """The edition's anonymity question decides."""
        order = PretixOrder(order_code="ORDER123", conference=conference)
        order.set_is_anonymous_from_answers(
            normalised(mapped, pretix_order_data).answers
        )
        assert order.is_anonymous is False

        pretix_order_data["positions"][0]["answers"][1]["option_identifiers"] = [
            STAY_ANONYMOUS
        ]
        order.set_is_anonymous_from_answers(
            normalised(mapped, pretix_order_data).answers
        )
        assert order.is_anonymous is True

    def test_without_an_anonymity_question_donors_stay_anonymous(
        self, pretix_order_data, conference, mapped
    ):
        mapped.anonymous_question = ""
        mapped.save()
        order = PretixOrder(order_code="ORDER123", conference=conference)
        order.set_is_anonymous_from_answers(
            normalised(mapped, pretix_order_data).answers
        )
        assert order.is_anonymous is True

    def test_from_a_pretix_registration(self, pretix_order_data, conference, mapped):
        order = PretixOrder(order_code=pretix_order_data["code"], conference=conference)
        order.from_registration(normalised(mapped, pretix_order_data))
        assert order.status == pretix_order_data["status"]
        assert order.email == pretix_order_data["email"]
        assert order.total == Decimal(pretix_order_data["total"])
        assert (order.state, order.kind, order.provider) == ("paid", "ticket", "PRETIX")
        assert order.cancellation_date == pretix_order_data["cancellation_date"]
        assert order.url == pretix_order_data["url"]
        assert order.datetime == pretix_order_data["datetime"]
        assert order.last_modified == pretix_order_data["last_modified"]
        assert order.event_slug == pretix_order_data["event"]
        assert order.name == "Example Attendee"
        assert order.is_anonymous is False
        assert order.raw_data == pretix_order_data


@pytest.mark.django_db
class TestAttendeeProfileModel:

    def test_attendee_profile_str_representation(self, conference):
        """Test string representation of AttendeeProfile."""
        order = PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        profile = AttendeeProfile(order=order)
        assert str(profile) == "Profile for ORDER123"

    def test_fills_the_mapped_fields(self, conference):
        order = PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        profile = AttendeeProfile(order=order).from_answers(FULL_ANSWERS)
        assert profile.city == "Vancouver"
        assert profile.country == "United States"
        assert profile.may_share_email_with_sponsor is True
        assert profile.experience_level == "Junior"
        assert profile.expectation_from_event == [
            "Networking",
            "Learn new things",
            "Support community activities",
        ]
        assert profile.heard_about == ["Social Media", "Other"]
        # Kept whole: the first-time answer is matched exactly.
        assert profile.participated_in_previous_event == ["No, this is my first one"]
        assert profile.age_range == "19-25"
        assert profile.organization_name == "Umbrella Corp"
        assert profile.current_position == ["Student/Intern", "Other"]
        assert profile.raw_answers == FULL_ANSWERS

    def test_unanswered_fields_are_cleared(self, conference):
        order = PretixOrder.objects.create(order_code="ORDER456", conference=conference)
        profile = AttendeeProfile(order=order).from_answers([])
        assert profile.city is None
        assert profile.country is None
        assert profile.may_share_email_with_sponsor is None
        assert profile.experience_level is None
        assert profile.expectation_from_event == []
        assert profile.heard_about == []
        assert profile.participated_in_previous_event == []
        assert profile.age_range is None
        assert profile.organization_name is None
        assert profile.current_position == []
        assert profile.raw_answers == []

    def test_none_as_an_answer_is_blank(self, conference):
        order = PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        profile = AttendeeProfile(order=order).from_answers(answers((CITY, "None")))
        assert profile.city is None


@pytest.mark.django_db
class TestQuestionMap:
    def test_an_unmapped_edition_fills_nothing(self, conference, mapped):
        mapped.question_map = {}
        mapped.save()
        order = PretixOrder.objects.create(order_code="ORDER9", conference=conference)
        given = answers((CITY, "Lima"))
        profile = AttendeeProfile(order=order).from_answers(given)
        assert profile.city is None
        assert profile.raw_answers == given


@pytest.mark.django_db
class TestPretixOrderConferenceLink:
    """Conference FK is required (non-null) as of multi-year Phase 4."""

    def test_links_to_conference(self, conference):
        order = PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        assert list(conference.pretix_orders.all()) == [order]
