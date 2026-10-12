"""Neutral question and answer ids for the ticketing tests, and a factory
for an edition's ticketing row with them mapped (decision 0012). The ids
that used to live in the attendee app were PyLadiesCon's own shop."""

from ticketing.models import TicketingSettings

ANONYMOUS_QUESTION = "ANONQ001"
STAY_ANONYMOUS = "ANONYES1"
NOT_ANONYMOUS = "ANONNO01"

CITY = "QCITY001"
COUNTRY = "QCNTRY01"
CURRENT_POSITION = "QPOS0001"
EXPERIENCE_LEVEL = "QEXP0001"
MAY_SHARE_EMAIL = "QSHARE01"
EXPECTATION = "QEXPCT01"
HEARD_ABOUT = "QHEARD01"
PARTICIPATED_BEFORE = "QPREV001"
CHAPTER = "QCHAP001"
AGE_RANGE = "QAGE0001"
ORGANIZATION = "QORG0001"

QUESTION_MAP = {
    CITY: "city",
    COUNTRY: "country",
    CURRENT_POSITION: "current_position",
    EXPERIENCE_LEVEL: "experience_level",
    MAY_SHARE_EMAIL: "may_share_email_with_sponsor",
    EXPECTATION: "expectation_from_event",
    HEARD_ABOUT: "heard_about",
    PARTICIPATED_BEFORE: "participated_in_previous_event",
    CHAPTER: "pyladies_chapter",
    AGE_RANGE: "age_range",
    ORGANIZATION: "organization_name",
}


def make_ticketing(conference, **kwargs):
    """A Pretix ticketing row with an API, the questions mapped and the
    anonymity question set; any field can be overridden."""
    values = {
        "organizer": "flashlights",
        "event_id": conference.slug,
        "api_token": "tok-secret",
        "webhook_secret": "hook-secret",
        "question_map": dict(QUESTION_MAP),
        "anonymous_question": ANONYMOUS_QUESTION,
        "anonymous_answer": STAY_ANONYMOUS,
    }
    values.update(kwargs)
    row, _ = TicketingSettings.objects.update_or_create(
        conference=conference, defaults=values
    )
    return row
