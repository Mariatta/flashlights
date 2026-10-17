from django.urls import path

from . import views

app_name = "community_app"
prefix = "community/"

urlpatterns = [path("hello/", views.hello, name="hello")]
