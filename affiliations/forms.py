"""The inline rows a person edits on their profile page."""

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory

from .models import Affiliation


class AffiliationForm(forms.ModelForm):
    class Meta:
        model = Affiliation
        fields = ["kind", "name", "url"]
        widgets = {
            "name": forms.TextInput(
                attrs={"list": "affiliation-names", "placeholder": "Name"}
            ),
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
        }


#: One blank row to start with; the page adds more without a round trip.
AffiliationFormSet = inlineformset_factory(
    get_user_model(),
    Affiliation,
    form=AffiliationForm,
    extra=1,
    can_delete=True,
)
