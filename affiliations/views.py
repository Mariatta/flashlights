"""Mix the affiliation rows into a profile form page.

The volunteer profile views are upstream code; this mixin is the one hook
they take. It renders the formset next to the main form and saves it only
when both validate, so a bad row never loses the rest of the profile. The
account profile, the speaker profile and the propose page take the same
mixin, so the rows are one record of the person's, wherever they edit it.
"""

from .forms import AffiliationFormSet
from .models import Affiliation


class AffiliationFormsetMixin:
    """For a ``CreateView`` or ``UpdateView`` whose user is ``request.user``."""

    #: Not ``prefix``: that name is the main form's, through FormMixin.
    affiliation_prefix = "affiliations"

    def get_affiliation_formset(self):
        """Bound to the POST when the page's rows were submitted; unbound
        (and left alone on save) when a client posted the profile fields
        only, so the profile form keeps working without the rows."""
        if not hasattr(self, "_affiliation_formset"):
            data = None
            if f"{self.affiliation_prefix}-TOTAL_FORMS" in self.request.POST:
                data = self.request.POST
            # A page that also serves signed-out visitors (the propose
            # page) has no rows to show them.
            self._affiliation_formset = (
                AffiliationFormSet(
                    data, instance=self.request.user, prefix=self.affiliation_prefix
                )
                if self.request.user.is_authenticated
                else None
            )
        return self._affiliation_formset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        formset = self.get_affiliation_formset()
        context["affiliation_formset"] = formset
        # Existing names, so "PyCon US" is spelled one way across people.
        context["affiliation_names"] = (
            Affiliation.objects.order_by("name")
            .values_list("name", flat=True)
            .distinct()
            if formset is not None
            else []
        )
        return context

    def form_valid(self, form):
        formset = self.get_affiliation_formset()
        if formset.is_bound and not formset.is_valid():
            return self.form_invalid(form)
        response = super().form_valid(form)
        if formset.is_bound:
            formset.save()
        return response
