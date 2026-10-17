from django.http import HttpResponse
from django.urls import path


def ping(request):
    return HttpResponse("pong")


urlpatterns = [path("ping/", ping, name="ping")]
