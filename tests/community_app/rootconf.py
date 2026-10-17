"""A root URL configuration with two community apps in front of the core's."""

from portal import community
from portal.urls import urlpatterns as core

urlpatterns = (
    community.urlpatterns(["tests.community_app", "tests.community_plain"]) + core
)
