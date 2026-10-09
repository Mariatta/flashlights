from django.contrib import admin

from .models import Affiliation


@admin.register(Affiliation)
class AffiliationAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "name", "url")
    list_filter = ("kind",)
    search_fields = ("name", "user__username", "user__email")
    autocomplete_fields = ("user",)
