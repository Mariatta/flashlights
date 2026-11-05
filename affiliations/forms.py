"""The inline rows a person edits on their profile page.

The rows are rendered field by field (``affiliations/_row.html``), not
through ``bootstrap_form``, so the widgets carry Bootstrap's classes
themselves; every page that includes the formset gets styled inputs.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import Affiliation


class AffiliationForm(forms.ModelForm):
    class Meta:
        model = Affiliation
        fields = ["kind", "name", "url"]
        widgets = {
            "kind": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "list": "affiliation-names",
                    "placeholder": "Name",
                }
            ),
            "url": forms.URLInput(
                attrs={"class": "form-control", "placeholder": "https://"}
            ),
        }


class BaseAffiliationFormSet(BaseInlineFormSet):
    """The formset adds the Remove box after the form is built, so it is
    styled here rather than on the form."""

    def add_fields(self, form, index):
        super().add_fields(form, index)
        if "DELETE" in form.fields:
            form.fields["DELETE"].widget.attrs["class"] = "form-check-input"


#: One blank row to start with; the page adds more without a round trip.
AffiliationFormSet = inlineformset_factory(
    get_user_model(),
    Affiliation,
    form=AffiliationForm,
    formset=BaseAffiliationFormSet,
    extra=1,
    can_delete=True,
)
