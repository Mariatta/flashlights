"""Choosing the edition the program pages work on (``speakers.editions``)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import Resolver404, resolve
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from .editions import program_editions, set_working_edition
from .permissions import can_work_sessions


def _same_page_in(target):
    """Whether ``target`` reads the same in another edition: a list or
    board does, a page of one session or presenter belongs to the edition
    it was opened in."""
    try:
        return not resolve(target.split("?", 1)[0]).kwargs
    except Resolver404:
        return False


class WorkingEditionView(LoginRequiredMixin, View):
    """Switch to the active edition or a newer one with the speaker portal
    on, and go back to the page the switch was made from, or to the
    sessions when that page was one of the old edition's."""

    http_method_names = ["post"]

    def post(self, request):
        value = request.POST.get("edition", "")
        chosen = next(
            (one for one in program_editions(request) if str(one.pk) == value), None
        )
        if chosen is None or not can_work_sessions(request.user, chosen):
            raise Http404("No such edition to plan.")
        set_working_edition(request, chosen)
        messages.success(request, f"You are working on {chosen.name}.")
        target = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}
        ) or not _same_page_in(target):
            target = "speakers:session_list"
        return redirect(target)
