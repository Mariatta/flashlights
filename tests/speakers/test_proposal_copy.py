"""The proposal receipt is a copy of the proposal: what the speaker wrote
about the session and their public answers, to everyone on it, once."""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from common.markdown_emails import MarkdownEmailRenderer, text_keeping_verbatim
from common.send_emails import send_email
from speakers.constants import AnswerVisibility, QuestionAbout, QuestionKind
from speakers.emails import send_proposal_received_email
from speakers.models import Proposal, ProposalAnswer, ProposalQuestion
from speakers.program_types import session_type
from speakers.seeds import seed_checklists
from speakers.services import submit_proposal

from .factories import add_presenter, make_presenter, make_session, make_settings

PROPOSE = reverse("speakers:propose")
MINE = reverse("speakers:my_proposals")

OUTLINE = "- Why tests\n- How: see [the docs](https://docs.example/tests)"


@pytest.fixture
def enabled(conference):
    settings_row = make_settings(conference, proposals_open=True)
    seed_checklists(conference)
    return settings_row


@pytest.fixture
def stranger(db):
    return User.objects.create_user(username="sam", email="sam@example.com")


def ask(conference, label, **kwargs):
    kwargs.setdefault("about", QuestionAbout.SESSION)
    kwargs.setdefault("kind", QuestionKind.SHORT_TEXT)
    kwargs.setdefault("visibility", AnswerVisibility.PUBLIC)
    return ProposalQuestion.objects.create(conference=conference, label=label, **kwargs)


def receipts():
    return [m for m in mail.outbox if "We have your proposal" in m.subject]


def html(message):
    return message.alternatives[0][0]


def proposed(conference, stranger, **fields):
    """A proposal over the service, with the session fields given."""
    presenter = make_presenter(
        conference, display_name="Sam", user=stranger, email=stranger.email
    )
    fields.setdefault("summary_md", "What testing is for.")
    session = make_session(conference, kind="TALK", title="Testing", **fields)
    add_presenter(session, presenter)
    return submit_proposal(presenter, session)


@pytest.mark.django_db
class TestTheCopy:
    def test_the_form_sends_a_copy_of_what_was_written(
        self, client, conference, enabled, stranger
    ):
        client.force_login(stranger)
        client.post(
            PROPOSE,
            {
                "you-display_name": "Sam Newcomer",
                "you-bio_md": "I write tests every day.",
                "you-timezone": "UTC",
                "session-kind": session_type(conference, "TALK").pk,
                "session-title": "A talk about testing",
                "session-summary_md": "What **testing** is for.",
                "session-outline_md": OUTLINE.replace("\n", "\r\n"),
                "session-audience_md": "Anyone who ships code.",
                "session-level": "ALL",
                "session-language": "en",
            },
        )
        (receipt,) = receipts()
        assert receipt.to == ["sam@example.com"]
        body = receipt.body
        assert "A talk about testing" in body
        assert "Kind: Talk" in body
        assert "Language: en" in body
        assert "minutes" in body
        assert "Anyone who ships code." in body
        # The plain-text part keeps their Markdown as typed: the bullets and
        # the address behind the link would be lost to stripping.
        assert OUTLINE in body
        assert "What **testing** is for." in body
        # The HTML part renders it.
        assert "<li>Why tests</li>" in html(receipt)
        assert 'href="https://docs.example/tests"' in html(receipt)
        assert "<strong>testing</strong>" in html(receipt)
        # No bio; the link to change it stays.
        assert "I write tests every day." not in body
        assert MINE in body

    def test_blank_fields_and_the_teams_notes_stay_out(
        self, conference, enabled, stranger
    ):
        proposal = proposed(
            conference, stranger, notes_md="Team only: maybe a keynote."
        )
        send_proposal_received_email(proposal)
        body = receipts()[0].body
        assert "What testing is for." in body
        assert "keynote" not in body
        for label in ("Outline", "Prerequisites", "Audience", "Level", "Language"):
            assert label not in body

    def test_only_answers_to_public_questions_are_copied(
        self, conference, enabled, stranger
    ):
        proposal = proposed(conference, stranger)
        session, presenter = proposal.session, proposal.presenter
        shown = ask(conference, "Tags", kind=QuestionKind.SHORT_TEXT)
        story = ask(conference, "Longer story", kind=QuestionKind.LONG_TEXT)
        blank = ask(conference, "Anything else")
        access = ask(
            conference,
            "Access needs",
            about=QuestionAbout.SPEAKER,
            visibility=AnswerVisibility.ORGANIZERS,
        )
        travel = ask(conference, "Travel", visibility=AnswerVisibility.TEAM)
        handle = ask(conference, "Handle", about=QuestionAbout.SPEAKER)
        for question, value in (
            (shown, "[testing](https://x.example)"),
            (story, "1. first\r\n2. second"),
            (blank, ""),
            (travel, "Flying from Lima"),
        ):
            ProposalAnswer.objects.create(
                question=question, session=session, value=value
            )
        ProposalAnswer.objects.create(
            question=access, presenter=presenter, value="A step-free room"
        )
        ProposalAnswer.objects.create(
            question=handle, presenter=presenter, value="@sam"
        )
        send_proposal_received_email(proposal)
        receipt = receipts()[0]
        body = receipt.body
        assert "1. first\n2. second" in body
        assert "@sam" in body
        assert "Anything else" not in body
        assert "step-free" not in body and "Access needs" not in body
        assert "Lima" not in body and "Travel" not in body
        # A short answer is read as words, not made into a link.
        assert 'href="https://x.example"' not in html(receipt)
        assert "[testing](https://x.example)" in html(receipt)


@pytest.mark.django_db
class TestWhoGetsIt:
    def test_everyone_on_the_proposal_gets_their_own_copy(
        self, conference, enabled, stranger
    ):
        proposal = proposed(conference, stranger)
        other = make_presenter(conference, display_name="Robin")
        add_presenter(proposal.session, other)
        handle = ask(conference, "Handle", about=QuestionAbout.SPEAKER)
        ProposalAnswer.objects.create(
            question=handle, presenter=proposal.presenter, value="@sam"
        )
        ProposalAnswer.objects.create(question=handle, presenter=other, value="@robin")
        mail.outbox.clear()
        assert send_proposal_received_email(proposal) == 2
        mine, theirs = receipts()
        assert mine.to == ["sam@example.com"]
        assert theirs.to == [other.email]
        assert "What testing is for." in theirs.body
        # The proposer is the one who can change it, so only they get the link.
        assert MINE in mine.body
        assert MINE not in theirs.body
        assert "Sam proposed a session" in theirs.body
        assert "Sam can change or withdraw it" in theirs.body
        # Each copy carries the recipient's own speaker answers only.
        assert "@sam" in mine.body and "@robin" not in mine.body
        assert "@robin" in theirs.body and "@sam" not in theirs.body

    def test_editing_a_submitted_proposal_sends_nothing(
        self, client, conference, enabled, stranger
    ):
        client.force_login(stranger)
        proposal = proposed(conference, stranger)
        mail.outbox.clear()
        client.post(
            reverse("speakers:proposal_edit", args=[proposal.pk]),
            {
                "session-kind": session_type(conference, "TALK").pk,
                "session-title": "Now retitled",
                "session-summary_md": "Changed.",
                "session-level": "ALL",
                "session-language": "en",
            },
        )
        assert Proposal.objects.get().session.title == "Now retitled"
        assert mail.outbox == []

    def test_queries_grow_only_by_the_cost_of_each_email(
        self, conference, enabled, stranger
    ):
        """Another presenter adds one email's queries and nothing else.

        The session's answers and every presenter's speaker answers are read
        once, whoever is on the session; what each recipient adds is the
        sending and its record, counted inside ``send_email``.
        """
        proposal = proposed(conference, stranger)
        handle = ask(conference, "Handle", about=QuestionAbout.SPEAKER)
        inside = []

        def counted_send(*args, **kwargs):
            with CaptureQueriesContext(connection) as captured:
                send_email(*args, **kwargs)
            inside.append(len(captured))

        def queries_outside_the_emails():
            other = make_presenter(conference, display_name="Robin")
            add_presenter(proposal.session, other)
            ProposalAnswer.objects.create(question=handle, presenter=other, value="@r")
            inside.clear()
            with CaptureQueriesContext(connection) as captured:
                send_proposal_received_email(proposal)
            return len(captured) - sum(inside)

        with patch("speakers.emails.send_email", counted_send):
            counts = [queries_outside_the_emails() for _ in range(3)]
        assert counts[0] == counts[1] == counts[2]


class TestTextKeepingVerbatim:
    def test_strings_are_kept_as_written_longest_first(self):
        markdown = "Intro with *em*.\n\n- a **b**\n\n- a **b** and more\n\n   \n"
        text = text_keeping_verbatim(
            MarkdownEmailRenderer(), markdown, ["- a **b**", "- a **b** and more", " "]
        )
        assert text == "Intro with em.\n\n- a **b**\n\n- a **b** and more"
