from django.urls import path

from . import views

urlpatterns = [
    path(
        "conferences/<int:pk>/tickets/",
        views.TicketingSettingsView.as_view(),
        name="conference_tickets",
    ),
]
