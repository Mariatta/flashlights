from collections import Counter

from django.core.cache import cache
from django.db.models import Count, Sum

from attendee.models import (
    AttendeeProfile,
    PretixOrder,
)
from portal.constants import (
    CACHE_KEY_ATTENDEE_BREAKDOWN,
    CACHE_KEY_ATTENDEE_COUNT,
    CACHE_KEY_ATTENDEE_FIRST_TIME_COUNT,
    CACHE_KEY_ATTENDEE_FIRST_TIME_PERCENT,
    CACHE_KEY_DONATION_BREAKDOWN,
    CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_DONATIONS_TOTAL_AMOUNT,
    CACHE_KEY_DONORS_COUNT,
    CACHE_KEY_HISTORICAL_COMPARISON,
    CACHE_KEY_SPONSORSHIP_BREAKDOWN,
    CACHE_KEY_SPONSORSHIP_COMMITTED,
    CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID,
    CACHE_KEY_SPONSORSHIP_PAID_COUNT,
    CACHE_KEY_SPONSORSHIP_PAID_PERCENT,
    CACHE_KEY_SPONSORSHIP_PENDING,
    CACHE_KEY_SPONSORSHIP_PENDING_COUNT,
    CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT,
    CACHE_KEY_TEAMS_COUNT,
    CACHE_KEY_TOTAL_FUNDS_RAISED,
    CACHE_KEY_TOTAL_SPONSORSHIPS,
    CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT,
    CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT,
    DONATIONS_GOAL,
    SPONSORSHIP_GOAL,
    STATS_CACHE_TIMEOUT,
)
from portal.models import Conference
from speakers.constants import ProposalDecision
from speakers.models import Proposal
from speakers.stats import get_task_stats_dict  # noqa: F401 (see below)
from sponsorship.models import (
    IndividualDonation,
    SponsorshipProfile,
    SponsorshipProgressStatus,
)
from ticketing.adapters import REGISTERED, Status
from ticketing.models import CHARTED_FIELDS, ProductKind, ticketing_for
from volunteer.constants import ApplicationStatus
from volunteer.models import Team, VolunteerProfile


def get_stats_cached_values(conference=None):
    """Collect some stats and return them in a dictionary.

    Returns an empty dict when there is no conference to report on (e.g. no
    active edition yet). Every stats helper keys its cache on
    ``conference.year``, so a ``None`` conference has nothing to compute;
    callers read stats with ``.get``/template lookups that tolerate the gap.
    """
    if conference is None:
        conference = Conference.get_active()
    stats_dict = {}
    if conference is None:
        return stats_dict

    stats_dict.update(get_volunteer_stats_dict(conference))

    stats_dict.update(get_sponsorships_stats_dict(conference))
    stats_dict.update(get_donations_stats_dict(conference))
    stats_dict.update(get_attendee_stats_dict(conference))
    # Task numbers are off the public page and its JSON for now (the
    # user's call, 23 September). ``get_task_stats_dict`` still works and
    # is still tested; putting them back is uncommenting this line.
    # stats_dict.update(get_task_stats_dict(conference))
    return stats_dict


def get_volunteer_stats_dict(conference):
    stats_dict = {}
    stats_dict[CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT] = get_volunteer_signup_stat_cache(
        conference
    )
    stats_dict[CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT] = (
        get_volunteer_onboarded_stat_cache(conference)
    )
    stats_dict[CACHE_KEY_TEAMS_COUNT] = get_volunteer_teams_stat_cache(conference)
    return stats_dict


def get_sponsorships_stats_dict(conference):
    stats_dict = {}
    stats_dict[SPONSORSHIP_GOAL] = conference.sponsorship_goal
    stats_dict[CACHE_KEY_TOTAL_SPONSORSHIPS] = get_sponsorship_total_count_stats_cache(
        conference
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_PAID] = get_sponsorship_paid_amount_stats_cache(
        conference
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_PAID_PERCENT] = get_sponsorship_paid_percent_cache(
        conference
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT] = (
        get_sponsorship_to_goal_percent_cache(conference)
    )

    stats_dict[CACHE_KEY_SPONSORSHIP_PENDING] = (
        get_sponsorship_pending_amount_stats_cache(conference)
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_COMMITTED] = (
        get_sponsorship_committed_amount_stats_cache(conference)
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_PAID_COUNT] = (
        get_sponsorship_paid_count_stats_cache(conference)
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_PENDING_COUNT] = (
        get_sponsorship_pending_count_stats_cache(conference)
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT] = (
        get_sponsorship_committed_count_stats_cache(conference)
    )
    stats_dict[CACHE_KEY_SPONSORSHIP_BREAKDOWN] = get_sponsorship_breakdown(conference)
    stats_dict[CACHE_KEY_TOTAL_FUNDS_RAISED] = get_total_donations_amount_cache(
        conference
    ) + get_sponsorship_committed_amount_stats_cache(conference)
    return stats_dict


def get_volunteer_signup_stat_cache(conference):
    """Returns the cached count of volunteer signups."""
    cache_key = f"{CACHE_KEY_VOLUNTEER_SIGNUPS_COUNT}_{conference.year}"
    volunteer_signups_count = cache.get(cache_key)
    if not volunteer_signups_count:
        volunteer_signups_count = VolunteerProfile.objects.filter(
            conference=conference
        ).count()
        cache.set(
            cache_key,
            volunteer_signups_count,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_signups_count


def get_volunteer_onboarded_stat_cache(conference):
    """Returns the cached count of volunteers onboarded."""
    cache_key = f"{CACHE_KEY_VOLUNTEER_ONBOARDED_COUNT}_{conference.year}"
    volunteer_onboarded_count = cache.get(cache_key)
    if not volunteer_onboarded_count:
        volunteer_onboarded_count = VolunteerProfile.objects.filter(
            application_status=ApplicationStatus.APPROVED.value, conference=conference
        ).count()
        cache.set(
            cache_key,
            volunteer_onboarded_count,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_onboarded_count


def get_volunteer_teams_stat_cache(conference):
    """Returns the cached count of volunteer teams."""
    cache_key = f"{CACHE_KEY_TEAMS_COUNT}_{conference.year}"
    volunteer_teams_count = cache.get(cache_key)
    if not volunteer_teams_count:
        volunteer_teams_count = Team.objects.filter(conference=conference).count()
        cache.set(
            cache_key,
            volunteer_teams_count,
            STATS_CACHE_TIMEOUT,
        )
    return volunteer_teams_count


SPONSOR_COMMITTED_STATUS = [
    SponsorshipProgressStatus.ACCEPTED,
    SponsorshipProgressStatus.APPROVED,
    SponsorshipProgressStatus.AGREEMENT_SENT,
    SponsorshipProgressStatus.AGREEMENT_SIGNED,
    SponsorshipProgressStatus.INVOICED,
    SponsorshipProgressStatus.PAID,
]
SPONSOR_PENDING_STATUS = [
    SponsorshipProgressStatus.ACCEPTED,
    SponsorshipProgressStatus.APPROVED,
    SponsorshipProgressStatus.AGREEMENT_SENT,
    SponsorshipProgressStatus.AGREEMENT_SIGNED,
    SponsorshipProgressStatus.INVOICED,
]
# "Committed but not yet invoiced" = committed statuses minus INVOICED/PAID.
# Used by the organizer dashboard's needs-attention queue.
SPONSOR_AWAITING_INVOICE_STATUS = [
    SponsorshipProgressStatus.ACCEPTED,
    SponsorshipProgressStatus.APPROVED,
    SponsorshipProgressStatus.AGREEMENT_SENT,
    SponsorshipProgressStatus.AGREEMENT_SIGNED,
]


def get_sponsorship_total_count_stats_cache(conference):
    """Returns total sponsorship count"""
    cache_key = f"{CACHE_KEY_TOTAL_SPONSORSHIPS}_{conference.year}"
    sponsorship_count = cache.get(cache_key)
    if not sponsorship_count:
        sponsorship_count = SponsorshipProfile.objects.filter(
            progress_status__gt=SponsorshipProgressStatus.NOT_CONTACTED,
            conference=conference,
        ).count()
        cache.set(cache_key, sponsorship_count, STATS_CACHE_TIMEOUT)
    return sponsorship_count


def get_sponsorship_paid_amount_stats_cache(conference):
    """Returns total sponsorship paid amount"""
    cache_key = f"{CACHE_KEY_SPONSORSHIP_PAID}_{conference.year}"
    cache.delete(cache_key)
    total_paid = cache.get(cache_key)
    if not total_paid:
        paid_sponsors = SponsorshipProfile.objects.filter(
            progress_status=SponsorshipProgressStatus.PAID, conference=conference
        )
        paid_sponsors_no_override_qs = paid_sponsors.filter(
            sponsorship_override_amount__isnull=True, sponsorship_tier__isnull=False
        )
        if paid_sponsors_no_override_qs:
            paid_sponsors_no_override = paid_sponsors_no_override_qs.aggregate(
                Sum("sponsorship_tier__amount")
            )["sponsorship_tier__amount__sum"]
        else:
            paid_sponsors_no_override = 0

        paid_sponsors_with_override_qs = paid_sponsors.filter(
            sponsorship_override_amount__isnull=False
        )
        if paid_sponsors_with_override_qs:

            paid_sponsors_with_override = paid_sponsors_with_override_qs.aggregate(
                Sum("sponsorship_override_amount")
            )["sponsorship_override_amount__sum"]
        else:
            paid_sponsors_with_override = 0

        total_paid = paid_sponsors_no_override + paid_sponsors_with_override
        total_paid = total_paid
        cache.set(cache_key, total_paid, STATS_CACHE_TIMEOUT)
    return total_paid


def get_sponsorship_pending_amount_stats_cache(conference):
    """Returns total sponsorship pending amount"""
    cache_key = f"{CACHE_KEY_SPONSORSHIP_PENDING}_{conference.year}"
    total_pending = cache.get(cache_key)
    if not total_pending:
        pending_sponsors = SponsorshipProfile.objects.filter(
            progress_status__in=SPONSOR_PENDING_STATUS, conference=conference
        )
        pending_sponsors_no_override_qs = pending_sponsors.filter(
            sponsorship_override_amount__isnull=True, sponsorship_tier__isnull=False
        )
        if pending_sponsors_no_override_qs:
            pending_sponsors_no_override = pending_sponsors_no_override_qs.aggregate(
                Sum("sponsorship_tier__amount")
            )["sponsorship_tier__amount__sum"]
        else:
            pending_sponsors_no_override = 0

        pending_sponsors_with_override_qs = pending_sponsors.filter(
            sponsorship_override_amount__isnull=False
        )
        if pending_sponsors_with_override_qs:
            pending_sponsors_with_override = (
                pending_sponsors_with_override_qs.aggregate(
                    Sum("sponsorship_override_amount")
                )["sponsorship_override_amount__sum"]
            )
        else:
            pending_sponsors_with_override = 0

        total_pending = pending_sponsors_no_override + pending_sponsors_with_override
        total_pending = total_pending

    cache.set(cache_key, total_pending, STATS_CACHE_TIMEOUT)
    return total_pending


def get_sponsorship_committed_amount_stats_cache(conference):
    """Returns total sponsorship committed amount"""
    cache_key = f"{CACHE_KEY_SPONSORSHIP_COMMITTED}_{conference.year}"
    total_committed = cache.get(cache_key)
    if not total_committed:
        committed_sponsors = SponsorshipProfile.objects.filter(
            progress_status__in=SPONSOR_COMMITTED_STATUS, conference=conference
        )
        committed_sponsors_no_override_qs = committed_sponsors.filter(
            sponsorship_override_amount__isnull=True, sponsorship_tier__isnull=False
        )
        if committed_sponsors_no_override_qs:
            committed_sponsors_no_override = (
                committed_sponsors_no_override_qs.aggregate(
                    Sum("sponsorship_tier__amount")
                )["sponsorship_tier__amount__sum"]
            )
        else:
            committed_sponsors_no_override = 0
        committed_sponsors_with_override_qs = committed_sponsors.filter(
            sponsorship_override_amount__isnull=False
        )
        if committed_sponsors_with_override_qs:
            committed_sponsors_with_override = (
                committed_sponsors_with_override_qs.aggregate(
                    Sum("sponsorship_override_amount")
                )["sponsorship_override_amount__sum"]
            )
        else:
            committed_sponsors_with_override = 0

        total_committed = (
            committed_sponsors_no_override + committed_sponsors_with_override
        )
        total_committed = total_committed
        cache.set(cache_key, total_committed, STATS_CACHE_TIMEOUT)
    return total_committed


def get_sponsorship_paid_count_stats_cache(conference):
    """Returns sponsorship paid count"""
    cache_key = f"{CACHE_KEY_SPONSORSHIP_PAID_COUNT}_{conference.year}"
    sponsorship_paid_count = cache.get(cache_key)
    if not sponsorship_paid_count:
        sponsorship_paid_count = SponsorshipProfile.objects.filter(
            progress_status=SponsorshipProgressStatus.PAID, conference=conference
        ).count()
        cache.set(
            cache_key,
            sponsorship_paid_count,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_paid_count


def get_sponsorship_pending_count_stats_cache(conference):
    """Returns sponsorship pending count"""
    cache_key = f"{CACHE_KEY_SPONSORSHIP_PENDING_COUNT}_{conference.year}"
    sponsorship_pending_count = cache.get(cache_key)
    if not sponsorship_pending_count:
        sponsorship_pending_count = SponsorshipProfile.objects.filter(
            progress_status__in=SPONSOR_PENDING_STATUS, conference=conference
        ).count()
        cache.set(
            cache_key,
            sponsorship_pending_count,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_pending_count


def get_sponsorship_committed_count_stats_cache(conference):
    """Returns sponsorship committed count"""
    cache_key = f"{CACHE_KEY_SPONSORSHIP_COMMITTED_COUNT}_{conference.year}"
    sponsorship_committed_count = cache.get(cache_key)
    if not sponsorship_committed_count:
        sponsorship_committed_count = SponsorshipProfile.objects.filter(
            progress_status__in=SPONSOR_COMMITTED_STATUS, conference=conference
        ).count()
        cache.set(
            cache_key,
            sponsorship_committed_count,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_committed_count


def get_sponsorship_to_goal_percent_cache(conference):
    """Returns sponsorship towards goal percent"""
    cache_key = f"{CACHE_KEY_SPONSORSHIP_TOWARDS_GOAL_PERCENT}_{conference.year}"
    sponsorship_towards_goal_percent = cache.get(cache_key)
    if not sponsorship_towards_goal_percent:
        total_paid = get_sponsorship_paid_amount_stats_cache(conference)
        sponsorship_towards_goal_percent = (
            (total_paid / conference.sponsorship_goal) * 100
            if conference.sponsorship_goal > 0
            else 0
        )
        cache.set(
            cache_key,
            sponsorship_towards_goal_percent,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_towards_goal_percent


def get_sponsorship_paid_percent_cache(conference):
    """Returns sponsorship paid percent"""
    cache_key = f"{CACHE_KEY_SPONSORSHIP_PAID_PERCENT}_{conference.year}"
    sponsorship_paid_percent = cache.get(cache_key)
    if not sponsorship_paid_percent:
        total_sponsorships = get_sponsorship_committed_amount_stats_cache(conference)
        total_paid_sponsorships = get_sponsorship_paid_amount_stats_cache(conference)
        sponsorship_paid_percent = (
            (total_paid_sponsorships / total_sponsorships) * 100
            if total_sponsorships > 0
            else 0
        )
        cache.set(
            cache_key,
            sponsorship_paid_percent,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_paid_percent


def get_sponsorship_breakdown(conference):
    cache_key = f"{CACHE_KEY_SPONSORSHIP_BREAKDOWN}_{conference.year}"
    sponsorship_breakdown = cache.get(cache_key)
    if not sponsorship_breakdown:
        sponsorship_breakdown = []

        # Breakdown by Status
        sponsors = SponsorshipProfile.objects.filter(
            progress_status__gt=SponsorshipProgressStatus.NOT_CONTACTED,
            conference=conference,
        ).select_related("sponsorship_tier")
        sponsors_by_status = sponsors.values("progress_status").annotate(
            count=Count("id")
        )
        result = [
            [SponsorshipProgressStatus(data["progress_status"]).label, data["count"]]
            for data in sponsors_by_status
        ]
        sponsorship_breakdown.append(
            {
                "title": "Sponsors By Status",
                "columns": [["string", "Progress"], ["number", "Count"]],
                "data": result,
                "chart_id": "sponsorship_by_status",
            }
        )

        # breakdown by Tier
        sponsors_by_tier = (
            sponsors.filter(sponsorship_tier__isnull=False)
            .values("sponsorship_tier__name")
            .annotate(count=Count("id"))
        )
        result = [
            [data["sponsorship_tier__name"], data["count"]] for data in sponsors_by_tier
        ]
        sponsorship_breakdown.append(
            {
                "title": "Sponsors By Tier",
                "columns": [["string", "Sponsorship Tier"], ["number", "Count"]],
                "data": result,
                "chart_id": "sponsorship_by_tier",
            }
        )

        cache.set(
            cache_key,
            sponsorship_breakdown,
            STATS_CACHE_TIMEOUT,
        )
    return sponsorship_breakdown


def get_total_donations_amount_cache(conference):
    """Returns the donations amount"""
    cache_key = f"{CACHE_KEY_DONATIONS_TOTAL_AMOUNT}_{conference.year}"
    total_donations = cache.get(cache_key)
    if not total_donations:

        individual_donations = (
            IndividualDonation.objects.filter(conference=conference).aggregate(
                Sum("donation_amount")
            )["donation_amount__sum"]
            or 0
        )
        donations_from_pretix = (
            PretixOrder.objects.filter(
                state=Status.PAID, kind=ProductKind.DONATION, conference=conference
            ).aggregate(Sum("total"))["total__sum"]
            or 0
        )
        total_donations = individual_donations + donations_from_pretix
        cache.set(
            cache_key,
            total_donations,
            STATS_CACHE_TIMEOUT,
        )
    return total_donations


def get_donors_count_cache(conference):
    """Returns the number of unique donors"""
    cache_key = f"{CACHE_KEY_DONORS_COUNT}_{conference.year}"
    donors_count = cache.get(cache_key)
    if not donors_count:

        individual_donors_count = (
            IndividualDonation.objects.filter(conference=conference)
            .values("donor_email")
            .distinct()
            .count()
        )
        pretix_donors_count = PretixOrder.objects.filter(
            state=Status.PAID,
            kind=ProductKind.DONATION,
            total__gt=0,
            conference=conference,
        ).count()
        donors_count = individual_donors_count + pretix_donors_count
        cache.set(
            cache_key,
            donors_count,
            STATS_CACHE_TIMEOUT,
        )
    return donors_count


def get_donation_to_goal_percent_cache(conference):
    """Returns donation towards goal percent"""
    cache_key = f"{CACHE_KEY_DONATION_TOWARDS_GOAL_PERCENT}_{conference.year}"
    donation_towards_goal_percent = cache.get(cache_key)
    if not donation_towards_goal_percent:
        total_donations = get_total_donations_amount_cache(conference)
        donation_towards_goal_percent = (
            (total_donations / conference.donation_goal) * 100
            if conference.donation_goal > 0
            else 0
        )
        cache.set(
            cache_key,
            donation_towards_goal_percent,
            STATS_CACHE_TIMEOUT,
        )
    return donation_towards_goal_percent


def get_donations_stats_dict(conference):
    stats_dict = {}
    stats_dict[DONATIONS_GOAL] = conference.donation_goal
    stats_dict[CACHE_KEY_DONATION_BREAKDOWN] = {
        "total_donations_amount": get_total_donations_amount_cache(conference),
        "donors_count": get_donors_count_cache(conference),
        "donation_towards_goal_percent": get_donation_to_goal_percent_cache(conference),
    }
    return stats_dict


def get_attendee_count_cache(conference):
    """Returns the attendee count"""
    cache_key = f"{CACHE_KEY_ATTENDEE_COUNT}_{conference.year}"
    attendee_count = cache.get(cache_key)
    if not attendee_count:
        attendee_count = PretixOrder.objects.filter(
            state__in=REGISTERED, kind=ProductKind.TICKET, conference=conference
        ).count()
        cache.set(
            cache_key,
            attendee_count,
            STATS_CACHE_TIMEOUT,
        )
    return attendee_count


def get_attendee_stats_dict(conference):
    stats_dict = {}
    stats_dict[CACHE_KEY_ATTENDEE_COUNT] = get_attendee_count_cache(conference)
    stats_dict[CACHE_KEY_ATTENDEE_BREAKDOWN] = get_attendee_breakdown(conference)
    stats_dict[CACHE_KEY_ATTENDEE_FIRST_TIME_COUNT] = get_first_time_attendee_count(
        conference
    )
    stats_dict[CACHE_KEY_ATTENDEE_FIRST_TIME_PERCENT] = get_first_time_attendee_percent(
        conference
    )
    stats_dict["attendee_first_time_on"] = bool(first_time_answer(conference))

    return stats_dict


def first_time_answer(conference):
    """The answer that means first time, when the edition maps the "came
    to a previous edition" question and says which answer that is."""
    row = ticketing_for(conference)
    if row is None or "participated_in_previous_event" not in set(
        row.question_map.values()
    ):
        return ""
    return row.first_time_answer


def get_first_time_attendee_count(conference):
    """Returns the count of first-time attendees."""
    cache_key = f"{CACHE_KEY_ATTENDEE_FIRST_TIME_COUNT}_{conference.year}"
    first_time_attendee_count = cache.get(cache_key)
    if not first_time_attendee_count:
        answer = first_time_answer(conference)
        first_time_attendee_count = (
            AttendeeProfile.objects.filter(
                order__state__in=REGISTERED,
                order__kind=ProductKind.TICKET,
                participated_in_previous_event__contains=[answer],
                order__conference=conference,
            ).count()
            if answer
            else 0
        )

        cache.set(
            cache_key,
            first_time_attendee_count,
            STATS_CACHE_TIMEOUT,
        )
    return first_time_attendee_count


def get_first_time_attendee_percent(conference):
    """Returns the percent of first-time attendees."""
    cache_key = f"{CACHE_KEY_ATTENDEE_FIRST_TIME_PERCENT}_{conference.year}"
    first_time_attendee_percent = cache.get(cache_key)
    if not first_time_attendee_percent:
        attendee_total_count = get_attendee_count_cache(conference)
        attendee_first_time_count = get_first_time_attendee_count(conference)
        first_time_attendee_percent = (
            (attendee_first_time_count / attendee_total_count) * 100
            if attendee_total_count > 0
            else 0
        )

        cache.set(
            cache_key,
            first_time_attendee_percent,
            STATS_CACHE_TIMEOUT,
        )
    return first_time_attendee_percent


def get_attendee_breakdown(conference):
    """One chart per attendee field the edition's question map fills: an
    edition that asks nothing shows no charts."""
    cache_key = f"{CACHE_KEY_ATTENDEE_BREAKDOWN}_{conference.year}"
    attendee_breakdown = cache.get(cache_key)
    if not attendee_breakdown:
        row = ticketing_for(conference)
        mapped = set((row.question_map if row else {}).values())
        profiles = AttendeeProfile.objects.filter(
            order__state__in=REGISTERED,
            order__kind=ProductKind.TICKET,
            order__conference=conference,
        )
        attendee_breakdown = [
            {"title": label, "data": get_attendee_field_breakdown(profiles, name)}
            for name, label in CHARTED_FIELDS
            if name in mapped
        ]
        cache.set(cache_key, attendee_breakdown, STATS_CACHE_TIMEOUT)
    return attendee_breakdown


def get_attendee_field_breakdown(attendee_profiles, field_name):
    """``[value, count]`` rows for one attendee field, sorted by value. A
    multiple-choice answer counts once per choice; a yes/no as Yes or No."""
    kind = AttendeeProfile._meta.get_field(field_name).get_internal_type()
    counts = Counter()
    for value in attendee_profiles.values_list(field_name, flat=True):
        if kind == "ChoiceArrayField":
            counts.update(part.strip() for part in value or [] if part and part.strip())
        elif kind == "BooleanField":
            if value is not None:
                counts["Yes" if value else "No"] += 1
        elif value:
            counts[value.strip()] += 1
    return [[value, count] for value, count in sorted(counts.items())]


def proposals_received(conference):
    """How many proposals the edition received: the number organizers typed
    in when their call for proposals ran somewhere else, else the portal's
    own proposals, leaving out the withdrawn ones."""
    if conference.proposals_count:
        return conference.proposals_count
    return (
        Proposal.objects.filter(conference=conference)
        .exclude(decision=ProposalDecision.WITHDRAWN)
        .count()
    )


def _conference_comparison_metrics(conference):
    """Per-year metrics for the comparison charts.

    Editions that predate the portal carry only a ``historical_snapshot``;
    everything else is aggregated live from that conference's records.
    """
    snapshot = conference.historical_snapshot
    if snapshot:
        sponsorship_amount = snapshot.get("sponsorship_amount", 0)
        donation_amount = snapshot.get("donation_amount", 0)
        metrics = {
            "registrations": snapshot.get("registrations", 0),
            "sponsors": snapshot.get("sponsors", 0),
            "donors": snapshot.get("donors", 0),
        }
    else:
        sponsorship_amount = get_sponsorship_committed_amount_stats_cache(conference)
        donation_amount = get_total_donations_amount_cache(conference)
        metrics = {
            "registrations": get_attendee_count_cache(conference),
            "sponsors": get_sponsorship_committed_count_stats_cache(conference),
            "donors": get_donors_count_cache(conference),
        }
    metrics["sponsorship_amount"] = sponsorship_amount
    metrics["donation_amount"] = donation_amount
    metrics["proposals"] = proposals_received(conference)
    metrics["proceeds"] = sponsorship_amount + donation_amount
    return metrics


def get_historical_comparison_data():
    """Year-over-year comparison charts built from every conference's data.

    Each edition contributes one bar per chart, taken from its live stats or,
    for editions that predate the portal, its ``historical_snapshot``.
    """
    historical_comparison = cache.get(CACHE_KEY_HISTORICAL_COMPARISON)
    if not historical_comparison:
        per_year = [
            (str(conference.year), _conference_comparison_metrics(conference))
            for conference in Conference.objects.order_by("year")
        ]
        charts = [
            ("Registrations Over the Years", "Registrations", "registrations"),
            ("Proposals Over the Years", "Proposals", "proposals"),
            ("Number of Sponsors Over the Years", "Sponsors", "sponsors"),
            (
                "Sponsorship Amount Over the Years",
                "Amount (USD)",
                "sponsorship_amount",
            ),
            ("Number of Individual Donors Over the Years", "Donors", "donors"),
            ("Donation Amount Over the Years", "Amount (USD)", "donation_amount"),
            ("Total Proceeds Over the Years", "Amount (USD)", "proceeds"),
        ]
        historical_comparison = [
            {
                "title": title,
                "columns": [["string", "Year"], ["number", value_label]],
                "data": [[year, metrics[key]] for year, metrics in per_year],
                "chart_id": f"{key}_comparison",
                "chart_type": "bar",
            }
            for title, value_label, key in charts
        ]
        cache.set(
            CACHE_KEY_HISTORICAL_COMPARISON,
            historical_comparison,
            STATS_CACHE_TIMEOUT,
        )

    return historical_comparison
