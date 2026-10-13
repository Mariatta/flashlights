"""Choosing the edition the program pages work on (``speakers.editions``)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from .editions import program_editions, set_working_edition
from .permissions import can_work_sessions


class WorkingEditionView(LoginRequiredMixin, View):
    """Switch to the active edition or a newer one with the speaker portal
    on, and go back to the page the switch was made from."""

    http_method_names = ["post"]

    def post(self, request):
        value = request.POST.get("edition", "")
        chosen = next((one for one in program_editions() if str(one.pk) == value), None)
        if chosen is None or not can_work_sessions(request.user, chosen):
            raise Http404("No such edition to plan.")
        set_working_edition(request, chosen)
        messages.success(request, f"You are working on {chosen.name}.")
        target = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}
        ):
            target = "speakers:session_list"
        return redirect(target)
