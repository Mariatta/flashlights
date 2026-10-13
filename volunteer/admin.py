from django.contrib import admin, messages
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from portal.admin_filters import ActiveConferenceFilter
from portal.models import Conference

from .constants import ApplicationStatus
from .models import Language, Team, VolunteerProfile


@admin.action(description="Mark selected Volunteers as waitlisted")
def bulk_waitlist_volunteers(modeladmin, request, queryset):
    """Waitlist the volunteers one by one.

    We want to trigger the email notification signal for each volunteers this way.
    """
    for volunteer in queryset:
        volunteer.application_status = ApplicationStatus.WAITLISTED
        volunteer.save()


@admin.action(description="Bring selected volunteers forward to the active event")
def bring_forward_to_active_conference(modeladmin, request, queryset):
    """Carry returning volunteers into the active edition without re-applying.

    Copies each selected profile's details into a new PENDING profile for the
    active conference; volunteers who already have a profile there are skipped.
    """
    active = Conference.get_active()
    if active is None:
        modeladmin.message_user(
            request, "No active event is set.", level=messages.ERROR
        )
        return
    created = 0
    skipped = 0
    for volunteer in queryset:
        if volunteer.bring_forward_to(active) is None:
            skipped += 1
        else:
            created += 1
    modeladmin.message_user(
        request,
        f"Brought {created} volunteer(s) forward into {active}; "
        f"{skipped} already had a profile there.",
        level=messages.SUCCESS,
    )


class VolunteerProfileResource(resources.ModelResource):
    # Export/import the conference by its year (stable, human-readable) rather
    # than the surrogate pk.
    conference = Field(
        attribute="conference",
        column_name="conference",
        widget=ForeignKeyWidget(Conference, field="year"),
    )

    def before_save_instance(self, instance, row, **kwargs):
        # during 'confirm' step, dry_run is True
        instance.from_import_export = True
        # Rows that omit the conference column belong to the active edition.
        if instance.conference_id is None:
            instance.conference = Conference.get_active()

    class Meta:
        model = VolunteerProfile
        fields = (
            "id",
            "conference",
            "user__first_name",
            "user__last_name",
            "user__email",
            "application_status",
            "github_username",
            "discord_username",
            "instagram_username",
            "bluesky_username",
            "mastodon_url",
            "x_username",
            "linkedin_url",
        )


class VolunteerProfileAdmin(ImportExportModelAdmin):
    list_display = (
        "user",
        "conference",
        "user__first_name",
        "user__last_name",
        "user__email",
        "availability_hours_per_week",
        "application_status",
        "creation_date",
        "modified_date",
    )
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "application_status",
    )
    list_filter = (ActiveConferenceFilter, "application_status")
    actions = [bulk_waitlist_volunteers, bring_forward_to_active_conference]
    resource_classes = [VolunteerProfileResource]
    # Dual-list ("available"/"chosen") pickers for the many-to-many fields.
    filter_horizontal = ("teams", "language")
    # ``languages_spoken`` is deprecated in favour of the ``language`` m2m; hide
    # it from the admin form (the public form already excludes it). The
    # region and the PyLadies chapter are upstream's own notions, kept on the
    # model and hidden everywhere in Flashlights; affiliations replace the
    # chapter, and PyLadies chapters have no admin page of their own.
    exclude = ("languages_spoken", "region", "chapter")


class TeamAdmin(admin.ModelAdmin):
    list_display = ("short_name", "conference", "open_to_new_members")
    list_filter = ("conference", "open_to_new_members")
    search_fields = ("short_name", "description")
    # The two permission sets and the leads as side-by-side boxes, the way
    # Django's own group page shows permissions.
    filter_horizontal = ("team_leads", "permissions", "lead_permissions")

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name in ("permissions", "lead_permissions"):
            # A permission's label reads its content type; without this the
            # box costs one query per permission on the site.
            queryset = kwargs.get("queryset", db_field.remote_field.model.objects)
            kwargs["queryset"] = queryset.select_related("content_type")
        return super().formfield_for_manytomany(db_field, request=request, **kwargs)


admin.site.register(Team, TeamAdmin)
admin.site.register(VolunteerProfile, VolunteerProfileAdmin)
admin.site.register(Language)
