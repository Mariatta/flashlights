from django.contrib.auth.mixins import PermissionRequiredMixin, UserPassesTestMixin
from django.http import Http404

from .constants import CHANGE_HANDBOOK, CHANGE_SETTINGS, CHANGE_TEMPLATES
from .editions import (
    module_enabled,
    queue_editions,
    speaker_edition,
    working_edition,
)
from .models import Presenter
from .permissions import (
    can_publish_program,
    can_publish_session_video,
    can_review_proposals,
    can_view_media,
    can_work_queue_in,
    can_work_sessions,
    is_speaker_organizer,
)


class SpeakerModuleRequiredMixin:
    """Hide every speaker-portal view until the edition opts in.

    Raises 404 (not 403) when the flag is off for the edition, so the
    module is invisible rather than merely locked while it is being built.
    ``self.conference`` is set for the view to scope its queries: the
    organizer's working edition (``speakers.editions``), which is the
    active one unless they chose to plan a newer one.
    """

    def get_edition(self):
        return working_edition(self.request)

    def dispatch(self, request, *args, **kwargs):
        self.conference = self.get_edition()
        if not module_enabled(self.conference, request):
            raise Http404("The speaker portal is not enabled for this edition.")
        return super().dispatch(request, *args, **kwargs)


class SpeakerStaffRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """Whoever reads the program (``speakers.view_program``), and liaisons.
    Querysets still scope what a liaison sees."""

    def test_func(self):
        return can_work_sessions(self.request.user, self.conference)


class SpeakerQueueRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """Organizers, liaisons, and volunteers carrying an organizer item.

    The digest mails an assignee a link to their queue, so the gate has to
    admit them; what they may then touch is narrowed per item.
    """

    def test_func(self):
        return can_work_queue_in(self.request.user, queue_editions(self.request))


class SpeakerOrganizerRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """Running the program (``speakers.manage_program``): creating sessions,
    inviting, publishing, deciding proposals, the pretix link."""

    def test_func(self):
        return is_speaker_organizer(self.request.user)


class SessionVideoRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """A session's video link, publish time and premiere
    (``speakers.publish_session_video``): the Recordings team's, whether or
    not they run the program."""

    def test_func(self):
        return can_publish_session_video(self.request.user)


class ProposalReviewRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """The proposal queue: program readers and liaisons read it, and a
    reviewer (``speakers.review_proposal``) who reads nothing else of the
    program may open it too."""

    def test_func(self):
        user = self.request.user
        return can_work_sessions(user, self.conference) or can_review_proposals(user)


class ProposalDecisionRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """Approving and declining: reviewers, and whoever runs the program."""

    def test_func(self):
        return can_review_proposals(self.request.user)


class MediaViewRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """The media team's pages: bulk downloads and exports
    (``speakers.view_mediaasset``)."""

    def test_func(self):
        return can_view_media(self.request.user)


class PublishingRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """What the public sees: the Publishing tabs (``speakers.publish_program``)."""

    def test_func(self):
        return can_publish_program(self.request.user)


class SpeakerSettingsRequiredMixin(SpeakerModuleRequiredMixin, PermissionRequiredMixin):
    """Types and roles, readiness gates: ``speakers.change_speakersettings``,
    the Program leads' permission."""

    permission_required = CHANGE_SETTINGS


class TemplateEditorRequiredMixin(SpeakerModuleRequiredMixin, PermissionRequiredMixin):
    """The checklist template editor: ``speakers.change_checklisttemplate``."""

    permission_required = CHANGE_TEMPLATES


class HandbookEditorRequiredMixin(SpeakerModuleRequiredMixin, PermissionRequiredMixin):
    """The speaker guides: ``speakers.change_handbook``."""

    permission_required = CHANGE_HANDBOOK


class PresenterRequiredMixin(SpeakerModuleRequiredMixin, UserPassesTestMixin):
    """The speaker side: the user must be a presenter in the edition they
    are on the program of (``speaker_edition``), which may be a newer one
    than the active edition.

    Sets ``self.presenter`` for the view; anyone without a presenter row
    gets 403 (the module is on, they are just not a speaker).
    """

    def get_edition(self):
        working = working_edition(self.request)
        return speaker_edition(self.request.user, working, self.request) or working

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        self.presenter = (
            Presenter.objects.filter(conference=self.conference, user=user)
            .select_related("liaison")
            .first()
        )
        # A proposer has a presenter row before anyone has said yes. The
        # speaker area belongs to people who are on the program, so being
        # a presenter is not enough: they need a session of the
        # conference's, which is what being onboarded means.
        return self.presenter is not None and self.presenter.is_onboarded
