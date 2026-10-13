from django.contrib import admin

from portal.admin_filters import ActiveConferenceFilter

from .constants import EventFormat, Recordings
from .models import (
    ActivityLog,
    AllowedOrigin,
    ChecklistItem,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Handbook,
    HandbookReadReceipt,
    Invitation,
    MediaAsset,
    Presenter,
    PresenterRole,
    Proposal,
    ReadinessGate,
    ReminderLog,
    Room,
    ScheduleSlot,
    Session,
    SessionPresenter,
    SessionType,
    SharedFileNotice,
    SpeakerSettings,
)


class AllowedOriginInline(admin.TabularInline):
    """Websites whose pages may read this edition's public API, one row
    each (the Publishing page lists them and links here)."""

    model = AllowedOrigin
    extra = 1
    fields = ("url",)
    verbose_name = "website allowed to show the program"
    verbose_name_plural = "websites allowed to show the program"


@admin.register(SpeakerSettings)
class SpeakerSettingsAdmin(admin.ModelAdmin):
    inlines = [AllowedOriginInline]
    list_display = (
        "conference",
        "speaker_module_enabled",
        "event_format",
        "recordings",
        "proposals_open",
        "media_for_speakers",
        "auto_transcribe",
        "default_premiere_location",
        "translation_languages",
    )
    #: Upstream's Pretix columns, unread since ticketing moved to its own
    #: app, kept off the form so nobody edits a dead value;
    #: and the voucher switch, off until voucher creation is built. Named
    #: rather than dropped in silence: the admin tests check that every
    #: editable field is offered or excluded.
    exclude = (
        "pretix_create_vouchers",
        "pretix_base_url",
        "pretix_organizer",
        "pretix_event",
        "pretix_api_token",
        "pretix_webhook_secret",
        "pretix_last_synced_at",
    )
    #: Settings an in-person edition has no use for.
    ONLINE_ONLY_FIELDS = (
        "default_premiere_location",
        "default_video_length_limit_minutes",
    )
    MEDIA_FIELDS = ("media_for_speakers", "auto_transcribe")

    def get_fieldsets(self, request, obj=None):
        """An in-person row has no use for the premiere and
        the video length limit; a row with no recordings has no Media."""
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None:
            return fieldsets
        drop = set()
        if obj.event_format == EventFormat.IN_PERSON:
            drop |= set(self.ONLINE_ONLY_FIELDS)
        if obj.recordings == Recordings.NONE:
            drop |= set(self.MEDIA_FIELDS)
        return tuple(
            (
                title,
                {
                    **options,
                    "fields": tuple(f for f in options["fields"] if f not in drop),
                },
            )
            for title, options in fieldsets
            if any(f not in drop for f in options["fields"])
        )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "conference",
                    "speaker_module_enabled",
                    "event_format",
                    "recordings",
                    "conference_timezone",
                    "organizers_email",
                )
            },
        ),
        (
            "Program",
            {
                "fields": (
                    "program_visibility",
                    "default_premiere_location",
                    "translation_languages",
                    "default_video_length_limit_minutes",
                )
            },
        ),
        (
            "Proposals",
            {
                "description": "While proposals are open, the landing page and the "
                "hubs offer the propose-a-session form to anyone with an account. "
                "Only session types marked open for proposals are offered.",
                "fields": ("proposals_open", "proposals_intro_md"),
            },
        ),
        (
            "Media",
            {
                "description": "The organizer side of the media pipeline (files on "
                "a session, the post-production board, exports) is always on. "
                "This switch opens the speaker side: their upload panel and "
                "the files shared with them.",
                "fields": ("media_for_speakers", "auto_transcribe"),
            },
        ),
    )
    list_filter = ("speaker_module_enabled", "proposals_open")
    list_select_related = ("conference",)


@admin.register(PresenterRole)
class PresenterRoleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "email_word",
        "sort_order",
        "is_active",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "is_active")
    search_fields = ("name", "code")
    list_select_related = ("conference",)


@admin.register(SessionType)
class SessionTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "is_content",
        "default_duration_minutes",
        "default_delivery",
        "sort_order",
        "is_active",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "is_content", "is_active")
    search_fields = ("name", "code")
    list_select_related = ("conference",)
    filter_horizontal = ("roles",)


class SessionPresenterInline(admin.TabularInline):
    model = SessionPresenter
    extra = 0
    fields = ("presenter", "role", "order", "confirmed_at")
    autocomplete_fields = ("presenter",)


class ScheduleSlotInline(admin.StackedInline):
    model = ScheduleSlot
    extra = 0
    fields = ("room", "start_utc", "end_utc")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "delivery", "status", "is_public", "conference")
    list_filter = (ActiveConferenceFilter, "kind", "delivery", "status", "is_public")
    search_fields = ("title", "slug")
    list_select_related = ("conference", "kind")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [SessionPresenterInline, ScheduleSlotInline]


@admin.register(Presenter)
class PresenterAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "email",
        "user",
        "liaison",
        "is_public",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "is_public")
    search_fields = ("display_name", "email", "slug")
    list_select_related = ("conference", "user", "liaison")
    autocomplete_fields = ("user", "liaison", "pretix_order")
    prepopulated_fields = {"slug": ("display_name",)}


@admin.register(SessionPresenter)
class SessionPresenterAdmin(admin.ModelAdmin):
    list_display = ("presenter", "session", "role", "order", "confirmed_at")
    list_filter = (ActiveConferenceFilter, "role")
    list_select_related = ("presenter", "session", "role", "conference")
    autocomplete_fields = ("session", "presenter")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "discord_id", "is_active", "conference")
    list_filter = (ActiveConferenceFilter, "kind", "is_active")
    search_fields = ("name", "discord_id")
    list_select_related = ("conference",)


@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ("session", "room", "start_utc", "end_utc", "conference")
    list_filter = (ActiveConferenceFilter, "room")
    list_select_related = ("session", "room", "conference")
    autocomplete_fields = ("session",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("creation_date", "action", "actor", "target", "conference")
    list_filter = (ActiveConferenceFilter, "action")
    list_select_related = ("actor", "conference", "content_type")
    readonly_fields = ("creation_date", "modified_date", "target")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = (
        "presenter",
        "session",
        "status",
        "sent_at",
        "opened_at",
        "accepted_at",
        "declined_at",
        "conference",
    )
    list_filter = (ActiveConferenceFilter,)
    search_fields = ("presenter__display_name", "presenter__email", "session__title")
    list_select_related = ("presenter", "session", "conference")
    autocomplete_fields = ("presenter", "session", "invited_by")
    readonly_fields = (
        "token",
        "sent_at",
        "expires_at",
        "opened_at",
        "accepted_at",
        "declined_at",
        "cancelled_at",
    )


class ChecklistTemplateItemInline(admin.TabularInline):
    model = ChecklistTemplateItem
    extra = 0
    fields = (
        "order",
        "owner",
        "title",
        "due_anchor",
        "due_offset_days",
        "auto_complete_rule",
        "requires_asset_kind",
        "requires_asset_language",
        "requires_handbook",
        "per_translation_language",
        "is_required",
        "assignee_default",
    )


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "scope",
        "kind",
        "role",
        "delivery",
        "is_active",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "scope", "kind", "is_active")
    search_fields = ("name",)
    list_select_related = ("conference",)
    inlines = [ChecklistTemplateItemInline]


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "status",
        "presenter",
        "session",
        "due_date",
        "assignee",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "owner", "status", "is_required")
    search_fields = ("title", "presenter__display_name", "session__title")
    list_select_related = ("presenter", "session", "assignee", "conference")
    autocomplete_fields = ("presenter", "session", "assignee", "template_item")
    # Status changes go through ``speakers.checklists.set_item_status`` (the
    # organizer views), which logs them, refuses to hand-tick automatic items
    # and re-tries the session's confirmation. The admin is for looking.
    readonly_fields = ("status", "note", "completed_by", "completed_at")


@admin.register(ChecklistTemplateItem)
class ChecklistTemplateItemAdmin(admin.ModelAdmin):
    """Registered so it can be an autocomplete target; edit items inline on
    the template instead."""

    list_display = ("title", "template", "owner", "order")
    search_fields = ("title", "template__name")
    list_select_related = ("template",)


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "kind",
        "language",
        "version",
        "status",
        "duration_seconds",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "kind", "status")
    search_fields = ("session__title",)
    list_select_related = ("session", "conference")
    autocomplete_fields = ("session", "uploaded_by")


class HandbookReadReceiptInline(admin.TabularInline):
    model = HandbookReadReceipt
    extra = 0
    fields = ("presenter", "read_at")
    readonly_fields = ("read_at",)
    autocomplete_fields = ("presenter",)


@admin.register(Handbook)
class HandbookAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "version", "published_at", "conference")
    list_filter = (ActiveConferenceFilter, "key")
    list_select_related = ("conference",)
    inlines = [HandbookReadReceiptInline]


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("item", "threshold_days", "recipient", "sent_at", "conference")
    list_filter = (ActiveConferenceFilter, "threshold_days")
    search_fields = ("recipient", "item__title")
    list_select_related = ("item", "conference")
    readonly_fields = ("sent_at",)


@admin.register(SharedFileNotice)
class SharedFileNoticeAdmin(admin.ModelAdmin):
    list_display = ("asset", "presenter", "recipient", "sent_at", "conference")
    list_filter = (ActiveConferenceFilter,)
    search_fields = ("recipient", "presenter__display_name", "asset__title")
    list_select_related = ("asset", "presenter", "conference")
    readonly_fields = ("sent_at",)


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ("session", "presenter", "decision", "submitted_at", "conference")
    list_filter = (ActiveConferenceFilter, "decision")
    search_fields = ("session__title", "presenter__display_name")
    list_select_related = ("session", "presenter", "conference")
    readonly_fields = ("conference", "submitted_at", "decided_at")


@admin.register(ReadinessGate)
class ReadinessGateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_open", "opened_at", "conference")
    list_filter = (ActiveConferenceFilter, "is_open")
    search_fields = ("code", "name")
    list_select_related = ("conference",)
    readonly_fields = ("opened_at", "opened_by")


@admin.register(HandbookReadReceipt)
class HandbookReadReceiptAdmin(admin.ModelAdmin):
    list_display = ("handbook", "presenter", "read_at", "conference")
    list_filter = (ActiveConferenceFilter,)
    search_fields = ("presenter__display_name", "handbook__title")
    list_select_related = ("handbook", "presenter", "conference")
    readonly_fields = ("read_at",)
