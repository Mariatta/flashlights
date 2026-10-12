import pytest

from attendee.models import AttendeeProfile, PretixOrder
from tests.ticketing_ids import (
    AGE_RANGE,
    CHAPTER,
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


@pytest.fixture(autouse=True)
def mapped(conference):
    """The edition's questions mapped (decision 0012): the attendee app
    no longer carries anyone's question ids."""
    return make_ticketing(conference)


@pytest.mark.django_db
class TestPretixOrderModel:

    def test_pretix_order_str_representation(self):
        """Test string representation of PretixOrder."""
        order = PretixOrder(order_code="ORDER123")
        assert str(order) == order.order_code

    def test_set_name_from_data(self, pretix_order_data):
        """Test populating PretixOrder name from pretix data."""
        order = PretixOrder(order_code="ORDER123")
        order.set_name_from_data(pretix_order_data)
        assert order.name == "Example Attendee"

    def test_anonymous_from_data(self, pretix_order_data, conference):
        """The edition's anonymity question decides."""
        order = PretixOrder(order_code="ORDER123", conference=conference)
        order.set_is_anonymous_from_data(pretix_order_data)
        assert order.is_anonymous is False

        pretix_order_data["positions"][0]["answers"][1]["option_identifiers"] = [
            STAY_ANONYMOUS
        ]
        order.set_is_anonymous_from_data(pretix_order_data)
        assert order.is_anonymous is True

    def test_without_an_anonymity_question_donors_stay_anonymous(
        self, pretix_order_data, conference, mapped
    ):
        mapped.anonymous_question = ""
        mapped.save()
        order = PretixOrder(order_code="ORDER123", conference=conference)
        order.set_is_anonymous_from_data(pretix_order_data)
        assert order.is_anonymous is True

    def test_set_data_from_pretix(self, pretix_order_data):
        """Test populating PretixOrder from pretix data."""
        order = PretixOrder(order_code=pretix_order_data["code"])
        order.from_pretix_data(pretix_order_data)
        assert order.status == pretix_order_data["status"]
        assert order.email == pretix_order_data["email"]
        assert order.total == pretix_order_data["total"]
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

    def test_populate_from_pretix_data(self, conference):
        """Test populating AttendeeProfile from pretix data."""
        order = PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        profile = AttendeeProfile(order=order)

        # Create sample pretix data with demographic answers
        pretix_data = {
            "code": "ORDER123",
            "positions": [
                {
                    "answers": [
                        {
                            "answer": "Vancouver",
                            "question_identifier": CITY,
                        },
                        {
                            "answer": "United States",
                            "question_identifier": COUNTRY,
                        },
                        {
                            "answer": "Networking, Learn new things, Support community activities",
                            "question_identifier": EXPECTATION,
                        },
                        {
                            "answer": "Social Media, Other",
                            "question_identifier": HEARD_ABOUT,
                        },
                        {
                            "answer": "No, this is my first one",
                            "question_identifier": PARTICIPATED_BEFORE,
                        },
                        {
                            "answer": "San Francisco",
                            "question_identifier": CHAPTER,
                        },
                        {
                            "answer": "19-25",
                            "question_identifier": AGE_RANGE,
                        },
                        {
                            "answer": "Umbrella Corp",
                            "question_identifier": ORGANIZATION,
                        },
                        {
                            "answer": "Student/Intern, Other",
                            "question_identifier": CURRENT_POSITION,
                        },
                        {
                            "answer": "Junior",
                            "question_identifier": EXPERIENCE_LEVEL,
                        },
                        {
                            "answer": "Yes, I'm interested",
                            "question_identifier": MAY_SHARE_EMAIL,
                        },
                    ],
                }
            ],
        }

        profile.from_pretix_data(pretix_data)

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
        assert profile.participated_in_previous_event == ["No this is my first one"]
        assert profile.pyladies_chapter == "San Francisco"
        assert profile.age_range == "19-25"
        assert profile.organization_name == "Umbrella Corp"
        assert profile.current_position == ["Student/Intern", "Other"]
        assert profile.raw_answers is not None

    def test_populate_from_pretix_data_handles_missing_fields(self, conference):
        """Test that from_pretix_data handles missing fields gracefully."""
        order = PretixOrder.objects.create(order_code="ORDER456", conference=conference)
        profile = AttendeeProfile(order=order)

        # Pretix data with minimal answers
        pretix_data = {
            "code": "ORDER456",
            "positions": [{"answers": []}],
        }

        profile.from_pretix_data(pretix_data)

        assert profile.city is None
        assert profile.country is None
        assert profile.may_share_email_with_sponsor is None
        assert profile.experience_level is None
        assert len(profile.expectation_from_event) == 0
        assert len(profile.heard_about) == 0
        assert len(profile.participated_in_previous_event) == 0
        assert profile.pyladies_chapter is None
        assert profile.age_range is None
        assert profile.organization_name is None
        assert len(profile.current_position) == 0
        assert profile.raw_answers is not None

    def test_populate_from_pretix_data_none_value_for_chapter(self, conference):
        """Test populating AttendeeProfile with all demographic fields."""
        order = PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        profile = AttendeeProfile(order=order)

        pretix_data = {
            "code": "ORDER123",
            "positions": [
                {
                    "answers": [
                        {
                            "answer": "Vancouver",
                            "question_identifier": CITY,
                        },
                        {
                            "answer": "United States",
                            "question_identifier": COUNTRY,
                        },
                        {
                            "answer": "Networking, Learn new things, Support community activities",
                            "question_identifier": EXPECTATION,
                        },
                        {
                            "answer": "Social Media, Other",
                            "question_identifier": HEARD_ABOUT,
                        },
                        {
                            "answer": "No, this is my first one",
                            "question_identifier": PARTICIPATED_BEFORE,
                        },
                        {
                            "answer": "None",
                            "question_identifier": CHAPTER,
                        },
                        {
                            "answer": "19-25",
                            "question_identifier": AGE_RANGE,
                        },
                        {
                            "answer": "Umbrella Corp",
                            "question_identifier": ORGANIZATION,
                        },
                        {
                            "answer": "Student/Intern, Other",
                            "question_identifier": CURRENT_POSITION,
                        },
                        {
                            "answer": "Junior",
                            "question_identifier": EXPERIENCE_LEVEL,
                        },
                        {
                            "answer": "Yes, I'm interested",
                            "question_identifier": MAY_SHARE_EMAIL,
                        },
                    ],
                }
            ],
        }

        profile.from_pretix_data(pretix_data)

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
        assert profile.participated_in_previous_event == ["No this is my first one"]
        assert profile.pyladies_chapter is None
        assert profile.age_range == "19-25"
        assert profile.organization_name == "Umbrella Corp"
        assert profile.current_position == ["Student/Intern", "Other"]
        assert profile.raw_answers is not None


@pytest.mark.django_db
class TestQuestionMap:
    def test_an_unmapped_edition_fills_nothing(self, conference, mapped):
        mapped.question_map = {}
        mapped.save()
        order = PretixOrder.objects.create(order_code="ORDER9", conference=conference)
        profile = AttendeeProfile(order=order).from_pretix_data(
            {
                "positions": [
                    {"answers": [{"question_identifier": CITY, "answer": "Lima"}]}
                ]
            }
        )
        assert profile.city is None
        assert profile.raw_answers == [{"question_identifier": CITY, "answer": "Lima"}]

    def test_order_resolves_its_edition_from_the_ticketing_event(self, conference):
        assert PretixOrder.resolve_conference(conference.slug) == conference


@pytest.mark.django_db
class TestPretixOrderConferenceLink:
    """Conference FK is required (non-null) as of multi-year Phase 4."""

    def test_links_to_conference(self, conference):
        order = PretixOrder.objects.create(order_code="ORDER123", conference=conference)
        assert list(conference.pretix_orders.all()) == [order]
