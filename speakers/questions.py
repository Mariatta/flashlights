"""The edition's own proposal questions: asking them, keeping the answers,
and deciding who reads them.

``ProposalQuestion`` rows (``speakers.models``) say what to ask; this
module turns them into a form (``QuestionAnswersForm``), writes the answers
back as ``ProposalAnswer`` rows, filters answers by who is reading
(``readable_answers``) and copies an edition's questions into the next one
(``clone_questions``). The views and the public API use these and never
build a field themselves.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from .constants import CHOICE_KINDS, AnswerVisibility, QuestionAbout, QuestionKind
from .models import Presenter, ProposalAnswer, ProposalQuestion
from .permissions import can_review_proposals, can_view_program, is_speaker_organizer

YES_NO_CHOICES = (("yes", "Yes"), ("no", "No"))


def active_questions(conference, about):
    """The questions the form asks, in order."""
    return ProposalQuestion.objects.filter(
        conference=conference, about=about, is_active=True
    )


def session_questions(conference):
    return active_questions(conference, QuestionAbout.SESSION)


def speaker_questions(conference):
    return active_questions(conference, QuestionAbout.SPEAKER)


class LinksField(forms.CharField):
    """One link per line, stored as a list. ``https://`` is assumed when a
    line has no scheme, as the handles do for a website."""

    widget = forms.Textarea(attrs={"rows": 3})
    default_error_messages = {"invalid": "“%(line)s” is not a link."}

    def prepare_value(self, value):
        if isinstance(value, list):
            return "\n".join(value)
        return value

    def to_python(self, value):
        text = super().to_python(value)
        links = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            if not line.startswith(("http://", "https://")):
                line = "https://" + line
            try:
                URLValidator()(line)
            except ValidationError:
                raise ValidationError(
                    self.error_messages["invalid"],
                    code="invalid",
                    params={"line": line},
                )
            links.append(line)
        return links


def build_field(question):
    """The form field a question is asked with. The visibility note is
    part of the help text, so the person answering reads who will see it
    before they type."""
    help_text = " ".join(
        part for part in (question.help_text.strip(), question.visibility_note) if part
    )
    common = {
        "label": question.label,
        "required": question.required,
        "help_text": help_text,
    }
    kind = question.kind
    if kind == QuestionKind.LONG_TEXT:
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), **common)
    if kind == QuestionKind.YES_NO:
        return forms.TypedChoiceField(
            choices=YES_NO_CHOICES,
            coerce=lambda value: value == "yes",
            empty_value=None,
            widget=forms.RadioSelect,
            **common,
        )
    if kind == QuestionKind.CHECKBOX:
        return forms.BooleanField(**common)
    if kind == QuestionKind.ONE_CHOICE:
        return forms.ChoiceField(
            choices=[(option, option) for option in question.option_list],
            widget=forms.RadioSelect,
            **common,
        )
    if kind == QuestionKind.MANY_CHOICES:
        return forms.MultipleChoiceField(
            choices=[(option, option) for option in question.option_list],
            widget=forms.CheckboxSelectMultiple,
            **common,
        )
    if kind == QuestionKind.LINK:
        return forms.URLField(assume_scheme="https", **common)
    if kind == QuestionKind.LINKS:
        return LinksField(**common)
    if kind == QuestionKind.NUMBER:
        return forms.IntegerField(**common)
    return forms.CharField(max_length=300, **common)


def initial_for(question, value):
    """A stored answer as the form shows it again."""
    if question.kind == QuestionKind.YES_NO:
        if value is None:
            return None
        return "yes" if value else "no"
    return value


def field_name(question):
    return f"q{question.pk}"


class QuestionAnswersForm(forms.Form):
    """The edition's questions about one subject (the session or the
    speaker), with the subject's answers so far as the initial values.

    ``save`` writes the answers to ``session`` or ``presenter``; a question
    switched off since the answer was given is left as it was.
    """

    def __init__(self, questions, *args, subject=None, **kwargs):
        self.questions = list(questions)
        self.subject = subject
        existing = {}
        if subject is not None and subject.pk:
            existing = {
                answer.question_id: answer.value
                for answer in subject.question_answers.all()
            }
        kwargs.setdefault("initial", {})
        for question in self.questions:
            if question.pk in existing:
                kwargs["initial"].setdefault(
                    field_name(question), initial_for(question, existing[question.pk])
                )
        super().__init__(*args, **kwargs)
        for question in self.questions:
            self.fields[field_name(question)] = build_field(question)

    def __bool__(self):
        """A form with no questions renders as nothing."""
        return bool(self.questions)

    def values(self):
        """``{question: value}`` in the stored shape."""
        return {
            question: self.cleaned_data.get(field_name(question))
            for question in self.questions
        }

    def save(self, subject=None):
        """Write the answers onto ``subject`` (a session or a presenter)."""
        subject = subject or self.subject
        column = "presenter" if isinstance(subject, Presenter) else "session"
        for question, value in self.values().items():
            ProposalAnswer.objects.update_or_create(
                question=question, **{column: subject}, defaults={"value": value}
            )


def can_read_answer(question, user, *, own=False):
    """Whether ``user`` reads an answer to ``question``: the person who gave
    it always does, everyone does for a public question, whoever runs the
    program (``speakers.manage_program``) does for the rest, and program
    readers and proposal reviewers for the team-visible ones."""
    if own or question.visibility == AnswerVisibility.PUBLIC:
        return True
    if is_speaker_organizer(user):
        return True
    return question.visibility == AnswerVisibility.TEAM and (
        can_review_proposals(user) or can_view_program(user)
    )


def readable_answers(subject, user, *, own=False, answers=None):
    """The subject's answers that ``user`` may read, blanks left out, in
    question order. Reads the prefetched ``question_answers`` unless
    ``answers`` (a queryset with the questions joined) is given."""
    if subject is None:
        return []
    if answers is None:
        answers = subject.question_answers.all()
    return [
        answer
        for answer in answers
        if not answer.is_blank and can_read_answer(answer.question, user, own=own)
    ]


def public_answers(subject):
    """The subject's answers to public questions, for the public program:
    ``[{"question", "kind", "value"}]``."""
    if subject is None:
        return []
    return [
        {
            "question": answer.question.label,
            "kind": answer.question.kind,
            "value": answer.value,
        }
        for answer in subject.question_answers.all()
        if answer.question.visibility == AnswerVisibility.PUBLIC and not answer.is_blank
    ]


def answers_queryset():
    """The prefetch every page that prints answers uses."""
    return ProposalAnswer.objects.select_related("question")


def clone_questions(target, source):
    """Copy ``source``'s active questions into ``target``, by label within
    what they are about, keeping whatever ``target`` already has. Returns
    how many were created."""
    created_count = 0
    for question in ProposalQuestion.objects.filter(conference=source, is_active=True):
        _, created = ProposalQuestion.objects.get_or_create(
            conference=target,
            about=question.about,
            label=question.label,
            defaults={
                "kind": question.kind,
                "help_text": question.help_text,
                "options": question.options,
                "required": question.required,
                "visibility": question.visibility,
                "order": question.order,
            },
        )
        created_count += created
    return created_count


def validate_options(kind, options):
    """The choice kinds need at least two choices; the others have none."""
    lines = [line.strip() for line in options.splitlines() if line.strip()]
    if kind in CHOICE_KINDS:
        if len(lines) < 2:
            raise ValidationError("Give at least two choices, one per line.")
        if len(set(lines)) != len(lines):
            raise ValidationError("Each choice should appear once.")
        return "\n".join(lines)
    return ""
