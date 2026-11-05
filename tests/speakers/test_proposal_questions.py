"""The edition's own questions on the proposal form: asked in the right
half, answered in the shape their kind gives them, read by the people the
question says, managed by organizers, copied between editions."""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from affiliations.models import Affiliation
from portal.models import Conference
from speakers.api import presenter_payload, session_payload
from speakers.constants import AnswerVisibility, QuestionAbout, QuestionKind
from speakers.models import ActivityLog, Proposal, ProposalAnswer, ProposalQuestion
from speakers.program_types import session_type
from speakers.questions import (
    LinksField,
    QuestionAnswersForm,
    clone_questions,
    initial_for,
    public_answers,
    readable_answers,
    validate_options,
)
from speakers.seeds import clone_speaker_setup, seed_checklists

from .factories import (
    add_presenter,
    make_presenter,
    make_published_slot,
    make_session,
    make_settings,
)

PROPOSE = reverse("speakers:propose")
QUEUE = reverse("speakers:proposal_queue")
QUESTIONS = reverse("speakers:proposal_questions")
NEW_QUESTION = reverse("speakers:proposal_question_create")
COPY = reverse("speakers:proposal_questions_copy")
MY_PROFILE = reverse("speakers:my_profile")


def ask(conference, label, **kwargs):
    kwargs.setdefault("about", QuestionAbout.SESSION)
    kwargs.setdefault("kind", QuestionKind.SHORT_TEXT)
    return ProposalQuestion.objects.create(conference=conference, label=label, **kwargs)


def q(question, value, prefix="answers"):
    return {f"{prefix}-q{question.pk}": value}


@pytest.fixture
def enabled(conference):
    settings_row = make_settings(conference, proposals_open=True)
    seed_checklists(conference)
    return settings_row


@pytest.fixture
def organizer(db, grant_organizer):
    return grant_organizer(
        User.objects.create_user(username="org", email="org@example.com", is_staff=True)
    )


@pytest.fixture
def reviewer(db, join_team):
    """Approves and declines, reads the program, runs nothing."""
    return join_team(
        User.objects.create_user(username="rev", email="rev@example.com"),
        "Proposal reviewers",
    )


@pytest.fixture
def stranger(db):
    return User.objects.create_user(username="sam", email="sam@example.com")


def proposal_post(conference, **extra):
    data = {
        "you-display_name": "Sam Newcomer",
        "you-bio_md": "I write tests.",
        "you-timezone": "UTC",
        "session-kind": session_type(conference, "TALK").pk,
        "session-title": "A talk about testing",
        "session-summary_md": "What testing is for.",
        "session-language": "en",
    }
    data.update(extra)
    return data


@pytest.mark.django_db
class TestAskingOnTheForm:
    def test_each_question_is_asked_in_its_half_with_who_reads_it(
        self, client, conference, enabled, stranger
    ):
        ask(conference, "Links to writing", kind=QuestionKind.LINKS)
        ask(
            conference,
            "Anything for the organizers?",
            visibility=AnswerVisibility.ORGANIZERS,
        )
        ask(
            conference,
            "First time speaking?",
            about=QuestionAbout.SPEAKER,
            kind=QuestionKind.YES_NO,
            visibility=AnswerVisibility.PUBLIC,
        )
        client.force_login(stranger)
        content = client.get(PROPOSE).content.decode()
        about, session = content.split('id="propose-your-session"')
        assert "First time speaking?" in about and "First time speaking?" not in session
        assert "Links to writing" in session and "Links to writing" not in about
        assert "Seen by the organizers only." in session
        assert "Seen by the organizers and the people reviewing proposals." in session
        assert "Published on your speaker profile if you are accepted." in about

    def test_a_required_question_blocks_sending(
        self, client, conference, enabled, stranger
    ):
        question = ask(conference, "Track", required=True)
        client.force_login(stranger)
        response = client.post(PROPOSE, proposal_post(conference))
        assert response.status_code == 200
        assert "This field is required" in response.content.decode()
        assert '1 in "Your session"' in response.content.decode()
        assert not Proposal.objects.exists()
        client.post(PROPOSE, proposal_post(conference, **q(question, "Main")))
        assert Proposal.objects.get().session.question_answers.get().value == "Main"

    def test_every_kind_stores_its_own_shape(
        self, client, conference, enabled, stranger
    ):
        kinds = {
            QuestionKind.SHORT_TEXT: ("Short", "a line", "a line"),
            QuestionKind.LONG_TEXT: ("Long", "two\nlines", "two\nlines"),
            QuestionKind.YES_NO: ("Before?", "yes", True),
            QuestionKind.CHECKBOX: ("I agree", "on", True),
            QuestionKind.ONE_CHOICE: ("Track", "Tools", "Tools"),
            QuestionKind.MANY_CHOICES: (
                "Fine with",
                ["Recorded", "Quoted"],
                ["Recorded", "Quoted"],
            ),
            QuestionKind.LINK: (
                "Slides",
                "example.org/slides",
                "https://example.org/slides",
            ),
            QuestionKind.LINKS: (
                "Writing",
                "example.org/a\n\nhttps://example.org/b",
                ["https://example.org/a", "https://example.org/b"],
            ),
            QuestionKind.NUMBER: ("Attendees so far", "0", 0),
        }
        questions, data = {}, proposal_post(conference)
        for kind, (label, posted, _) in kinds.items():
            options = "Main\nTools\nRecorded\nQuoted" if "CHOICE" in kind else ""
            questions[kind] = ask(conference, label, kind=kind, options=options)
            data.update(q(questions[kind], posted))
        client.force_login(stranger)
        assert client.post(PROPOSE, data).status_code == 302
        session = Proposal.objects.get().session
        stored = {a.question.kind: a for a in session.question_answers.all()}
        for kind, (_, _, expected) in kinds.items():
            assert stored[kind].value == expected, kind
        # Printed: numbers as digits (0 is an answer), lists joined, booleans as words.
        assert stored[QuestionKind.NUMBER].display == "0"
        assert stored[QuestionKind.MANY_CHOICES].display == "Recorded, Quoted"
        assert stored[QuestionKind.YES_NO].display == "Yes"
        assert stored[QuestionKind.LINKS].links == [
            "https://example.org/a",
            "https://example.org/b",
        ]
        assert stored[QuestionKind.LINK].links == ["https://example.org/slides"]
        assert stored[QuestionKind.SHORT_TEXT].links == []

    def test_a_line_that_is_not_a_link_is_refused(
        self, client, conference, enabled, stranger
    ):
        question = ask(conference, "Writing", kind=QuestionKind.LINKS)
        client.force_login(stranger)
        response = client.post(
            PROPOSE, proposal_post(conference, **q(question, "not a link at all"))
        )
        assert "is not a link" in response.content.decode()
        assert not Proposal.objects.exists()

    def test_a_switched_off_question_is_not_asked(
        self, client, conference, enabled, stranger
    ):
        ask(conference, "Old question", is_active=False)
        client.force_login(stranger)
        assert "Old question" not in client.get(PROPOSE).content.decode()

    def test_speaker_answers_are_given_once_and_shown_again(
        self, client, conference, enabled, stranger
    ):
        before = ask(
            conference,
            "Spoken before?",
            about=QuestionAbout.SPEAKER,
            kind=QuestionKind.YES_NO,
        )
        client.force_login(stranger)
        client.post(
            PROPOSE, proposal_post(conference, **q(before, "no", prefix="speaker"))
        )
        presenter = Proposal.objects.get().presenter
        assert presenter.question_answers.get().value is False
        # The second proposal shows the answer filled in and may change it.
        content = client.get(PROPOSE).content.decode()
        assert 'value="no"' in content and "checked" in content
        client.post(
            PROPOSE,
            {
                **proposal_post(conference, **q(before, "yes", prefix="speaker")),
                "session-title": "Another talk",
            },
        )
        assert presenter.question_answers.get().value is True
        assert Proposal.objects.count() == 2

    def test_editing_the_proposal_changes_the_session_answers(
        self, client, conference, enabled, stranger
    ):
        question = ask(conference, "Track")
        client.force_login(stranger)
        client.post(PROPOSE, proposal_post(conference, **q(question, "Main")))
        proposal = Proposal.objects.get()
        url = reverse("speakers:proposal_edit", args=[proposal.pk])
        assert 'value="Main"' in client.get(url).content.decode()
        response = client.post(
            url,
            {
                "session-kind": proposal.session.kind_id,
                "session-title": "A talk about testing",
                "session-summary_md": "What testing is for.",
                "session-language": "en",
                **q(question, "Tools"),
            },
        )
        assert response.status_code == 302
        assert proposal.session.question_answers.get().value == "Tools"
        # A bad answer keeps the page, with the error.
        response = client.post(
            url,
            {
                "session-kind": proposal.session.kind_id,
                "session-title": "A talk about testing",
                "session-summary_md": "What testing is for.",
                "session-language": "en",
                **q(question, "x" * 301),
            },
        )
        assert response.status_code == 200
        assert "at most 300 characters" in response.content.decode()

    def test_the_speaker_profile_asks_the_speaker_questions(
        self, client, conference, enabled
    ):
        user = User.objects.create_user(username="ada", email="ada@example.com")
        presenter = make_presenter(conference, display_name="Ada", user=user)
        add_presenter(make_session(conference), presenter, confirmed=True)
        question = ask(
            conference, "Happy to be", about=QuestionAbout.SPEAKER, required=True
        )
        ask(conference, "Not for the profile", about=QuestionAbout.SESSION)
        client.force_login(user)
        content = client.get(MY_PROFILE).content.decode()
        assert "Happy to be" in content and "Not for the profile" not in content
        response = client.post(MY_PROFILE, {"display_name": "Ada", "timezone": "UTC"})
        assert response.status_code == 200
        assert "This field is required" in response.content.decode()
        response = client.post(
            MY_PROFILE,
            {"display_name": "Ada", "timezone": "UTC", **q(question, "Recorded")},
        )
        assert response.status_code == 302
        assert presenter.question_answers.get().value == "Recorded"


@pytest.fixture
def answered(conference, enabled, stranger):
    """A pending proposal with one answer per visibility, and a speaker
    answer, as the proposer gave them."""
    private = ask(conference, "For organizers", visibility=AnswerVisibility.ORGANIZERS)
    team = ask(conference, "For the team", visibility=AnswerVisibility.TEAM)
    public = ask(conference, "For everyone", visibility=AnswerVisibility.PUBLIC)
    blank = ask(conference, "Left blank")
    speaker = ask(
        conference,
        "About me",
        about=QuestionAbout.SPEAKER,
        kind=QuestionKind.LONG_TEXT,
        visibility=AnswerVisibility.PUBLIC,
    )
    presenter = make_presenter(conference, display_name="Sam", user=stranger)
    session = make_session(conference, title="Answered talk", kind="TALK")
    add_presenter(session, presenter)
    proposal = Proposal.objects.create(session=session, presenter=presenter)
    for question, value in (
        (private, "secret"),
        (team, "shared"),
        (public, "open"),
        (blank, ""),
    ):
        ProposalAnswer.objects.create(question=question, session=session, value=value)
    ProposalAnswer.objects.create(
        question=speaker, presenter=presenter, value="first\nsecond"
    )
    return proposal


@pytest.mark.django_db
class TestWhoReadsAnswers:
    def test_a_program_reader_who_reviews_nothing_sees_only_public_answers(
        self, client, answered, join_team
    ):
        """The note promised "the organizers and the people reviewing
        proposals"; a Recordings member reads the program and is neither."""
        reader = join_team(
            User.objects.create_user(username="rec", email="rec@example.com"),
            "Recordings",
        )
        client.force_login(reader)
        content = client.get(answered.session.get_absolute_url()).content.decode()
        assert "open" in content and "shared" not in content and "secret" not in content

    def test_organizers_read_everything_reviewers_not_the_private_ones(
        self, client, answered, organizer, reviewer
    ):
        client.force_login(organizer)
        content = client.get(QUEUE).content.decode()
        assert "secret" in content and "shared" in content and "open" in content
        assert "Left blank" not in content
        assert "first<br>second" in content
        client.force_login(reviewer)
        content = client.get(QUEUE).content.decode()
        assert "secret" not in content and "For organizers" not in content
        assert "shared" in content and "open" in content

    def test_queue_queries_do_not_grow_with_the_proposals(
        self, client, answered, organizer
    ):
        """Every row prints the proposer's affiliations and the answers it
        may show; all of it is prefetched."""
        conference = answered.conference
        client.force_login(organizer)

        def count():
            with CaptureQueriesContext(connection) as context:
                client.get(QUEUE)
            return len(context)

        questions = list(ProposalQuestion.objects.filter(conference=conference))
        before = count()
        for n in range(4):
            user = User.objects.create_user(username=f"p{n}", email=f"p{n}@x.org")
            Affiliation.objects.create(user=user, name=f"Project {n}")
            presenter = make_presenter(conference, user=user)
            session = make_session(conference, kind="TALK")
            add_presenter(session, presenter)
            Proposal.objects.create(session=session, presenter=presenter)
            for question in questions:
                subject = (
                    {"presenter": presenter}
                    if question.is_about_speaker
                    else {"session": session}
                )
                ProposalAnswer.objects.create(
                    question=question, value=f"v{n}", **subject
                )
        assert count() == before
        content = client.get(QUEUE).content.decode()
        assert "(Project 3)" in content and "v3" in content

    def test_the_session_and_presenter_pages_print_them(
        self, client, answered, organizer
    ):
        client.force_login(organizer)
        content = client.get(answered.session.get_absolute_url()).content.decode()
        assert "Answers to the proposal questions" in content and "secret" in content
        url = reverse("speakers:presenter_detail", args=[answered.presenter.slug])
        content = client.get(url).content.decode()
        assert "Their answers" in content and "first<br>second" in content

    def test_the_proposer_reads_their_own(self, answered, stranger):
        own = readable_answers(answered.session, stranger, own=True)
        assert [a.value for a in own] == ["secret", "shared", "open"]
        # Not as the proposer: a stranger reads the public answer only.
        others = readable_answers(answered.session, stranger)
        assert [a.value for a in others] == ["open"]
        assert readable_answers(None, stranger) == []

    def test_only_public_answers_reach_the_public_api(self, answered):
        assert public_answers(answered.session) == [
            {"question": "For everyone", "kind": "SHORT_TEXT", "value": "open"}
        ]
        assert public_answers(None) == []
        session = answered.session
        make_published_slot(session)
        session.public_links = []
        payload = session_payload(session.conference, session, set(), "https://x")
        assert payload["answers"] == public_answers(session)
        payload = presenter_payload(answered.presenter, [], "https://x")
        assert payload["answers"][0]["value"] == "first\nsecond"


@pytest.mark.django_db
class TestOrganizerPages:
    def test_the_list_says_who_reads_each_answer(
        self, client, conference, enabled, organizer, reviewer
    ):
        ask(conference, "Track", kind=QuestionKind.ONE_CHOICE, options="Main\nTools")
        ask(
            conference,
            "About me",
            about=QuestionAbout.SPEAKER,
            visibility=AnswerVisibility.PUBLIC,
            is_active=False,
        )
        client.force_login(organizer)
        content = client.get(QUESTIONS).content.decode()
        assert "Organizers and proposal reviewers" in content
        assert "Everyone, on the public program" in content
        assert "Main, Tools" in content and "not asked" in content
        assert "Copy from another edition" not in content
        # The rail and the settings page point here.
        assert (
            "Proposal questions"
            in client.get(reverse("speakers:speaker_settings")).content.decode()
        )
        client.force_login(reviewer)
        assert client.get(QUESTIONS).status_code == 403

    def test_adding_a_question(self, client, conference, enabled, organizer):
        client.force_login(organizer)
        data = {
            "about": QuestionAbout.SESSION,
            "label": "  Track ",
            "help_text": "",
            "kind": QuestionKind.ONE_CHOICE,
            "options": "Main\n\nTools\n",
            "visibility": AnswerVisibility.PUBLIC,
            "order": 10,
            "is_active": "on",
        }
        response = client.post(NEW_QUESTION, {**data, "options": "Main"})
        assert "at least two choices" in response.content.decode()
        response = client.post(NEW_QUESTION, {**data, "options": "Main\nMain"})
        assert "should appear once" in response.content.decode()
        assert client.post(NEW_QUESTION, data).status_code == 302
        question = ProposalQuestion.objects.get()
        assert question.label == "Track" and question.options == "Main\nTools"
        assert ActivityLog.objects.filter(action="speakers.question_changed").exists()
        response = client.post(NEW_QUESTION, {**data, "label": "track"})
        assert "already a question with this wording" in response.content.decode()
        # A text question drops any choices typed by mistake.
        client.post(
            NEW_QUESTION, {**data, "label": "Notes", "kind": QuestionKind.LONG_TEXT}
        )
        assert ProposalQuestion.objects.get(label="Notes").options == ""

    def test_an_answered_question_keeps_its_shape(self, client, answered, organizer):
        question = ProposalQuestion.objects.get(label="For the team")
        client.force_login(organizer)
        url = reverse("speakers:proposal_question_edit", args=[question.pk])
        assert "Fixed: this question has answers" in client.get(url).content.decode()
        response = client.post(
            url,
            {
                "about": QuestionAbout.SPEAKER,
                "kind": QuestionKind.NUMBER,
                "label": "For the team, reworded",
                "help_text": "",
                "options": "A\nB",
                "visibility": AnswerVisibility.PUBLIC,
                "order": 5,
            },
        )
        assert response.status_code == 302
        question.refresh_from_db()
        assert question.label == "For the team, reworded"
        # The shape and the promise the answers were given under stay.
        assert question.kind == QuestionKind.SHORT_TEXT
        assert question.about == QuestionAbout.SESSION
        assert question.options == ""
        assert question.visibility == AnswerVisibility.TEAM
        assert question.is_active is False

    def test_deleting(self, client, answered, organizer):
        client.force_login(organizer)
        fresh = ask(answered.conference, "Nobody answered")
        content = client.get(QUESTIONS).content.decode()
        assert content.count("btn-outline-danger") == 1
        response = client.post(
            reverse("speakers:proposal_question_delete", args=[fresh.pk]), follow=True
        )
        assert "Deleted" in response.content.decode()
        assert not ProposalQuestion.objects.filter(pk=fresh.pk).exists()
        team = ProposalQuestion.objects.get(label="For the team")
        response = client.post(
            reverse("speakers:proposal_question_delete", args=[team.pk]), follow=True
        )
        assert "Switch it off instead" in response.content.decode()
        assert ProposalQuestion.objects.filter(pk=team.pk).exists()

    def test_copying_from_another_edition(self, client, conference, enabled, organizer):
        last_year = Conference.objects.create(
            name="Last year", year=conference.year - 1
        )
        ask(last_year, "Track", kind=QuestionKind.ONE_CHOICE, options="A\nB")
        ask(last_year, "About me", about=QuestionAbout.SPEAKER)
        ask(last_year, "Retired", is_active=False)
        ask(conference, "Track")
        client.force_login(organizer)
        content = client.get(QUESTIONS).content.decode()
        assert "Copy from another edition" in content and "Last year" in content
        response = client.post(COPY, {"source": last_year.pk}, follow=True)
        assert "Copied 1 question from Last year" in response.content.decode()
        labels = set(
            ProposalQuestion.objects.filter(conference=conference).values_list(
                "label", flat=True
            )
        )
        assert labels == {"Track", "About me"}
        response = client.post(COPY, {"source": last_year.pk}, follow=True)
        assert "Nothing to copy" in response.content.decode()
        response = client.post(COPY, {"source": conference.pk}, follow=True)
        assert "Pick an edition" in response.content.decode()
        assert (
            ActivityLog.objects.filter(action="speakers.questions_copied").count() == 2
        )

    def test_starting_next_year_carries_the_questions(self, conference, enabled):
        ask(conference, "Track")
        ask(conference, "Retired", is_active=False)
        target = Conference.objects.create(name="Next", year=conference.year + 1)
        counts = clone_speaker_setup(target, conference)
        assert counts["questions"] == 1
        assert clone_questions(target, conference) == 0


@pytest.mark.django_db
class TestTheParts:
    def test_display_and_options(self, conference):
        yes_no = ask(conference, "Before?", kind=QuestionKind.YES_NO)
        assert yes_no.display(None) == "" and yes_no.display(False) == "No"
        text = ask(conference, "Text")
        assert text.display(None) == "" and text.display("") == ""
        assert text.display([]) == "" and text.display(["a", "b"]) == "a, b"
        assert str(text) == "Text" and not text.has_options
        choice = ask(
            conference, "Pick", kind=QuestionKind.ONE_CHOICE, options=" A \n\nB"
        )
        assert choice.option_list == ["A", "B"] and choice.has_options
        answer = ProposalAnswer(question=text, value="hello")
        assert str(answer) == "Text: hello" and not answer.is_blank
        assert ProposalAnswer(question=text, value="").is_blank

    def test_initial_values_and_the_links_field(self, conference):
        yes_no = ask(conference, "Before?", kind=QuestionKind.YES_NO)
        assert initial_for(yes_no, None) is None
        assert initial_for(yes_no, True) == "yes"
        assert initial_for(ask(conference, "T"), "x") == "x"
        field = LinksField(required=False)
        assert field.prepare_value(["https://a", "https://b"]) == "https://a\nhttps://b"
        assert field.prepare_value("typed") == "typed"
        assert field.clean("") == []

    def test_validate_options(self):
        assert validate_options(QuestionKind.SHORT_TEXT, "junk") == ""
        with pytest.raises(ValidationError):
            validate_options(QuestionKind.MANY_CHOICES, "only one")

    def test_a_form_with_no_questions_is_nothing(self, conference):
        form = QuestionAnswersForm(ProposalQuestion.objects.none())
        assert not form and form.fields == {}
        question = ask(conference, "Track")
        form = QuestionAnswersForm([question], {f"q{question.pk}": "Main"})
        assert form and form.is_valid()
        session = make_session(conference)
        form.save(session)
        assert session.question_answers.get().value == "Main"
        presenter = make_presenter(conference)
        speaker = ask(conference, "Me", about=QuestionAbout.SPEAKER)
        form = QuestionAnswersForm(
            [speaker], {f"q{speaker.pk}": "yes"}, subject=presenter
        )
        assert form.is_valid()
        form.save()
        assert presenter.question_answers.get().value == "yes"
