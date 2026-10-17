from django.shortcuts import render


def hello(request):
    return render(request, "community_app/hello.html")
