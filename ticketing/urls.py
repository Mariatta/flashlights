from django.urls import path

from . import views

urlpatterns = [
    path(
        "events/<int:pk>/tickets/",
        views.TicketingSettingsView.as_view(),
        name="conference_tickets",
    ),
    path(
        "events/<int:pk>/tickets/import/",
        views.CsvImportView.as_view(),
        name="conference_tickets_import",
    ),
]
