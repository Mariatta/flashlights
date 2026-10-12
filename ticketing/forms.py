from django import forms

from .models import (
    ATTENDEE_FIELD_NAMES,
    CSV_FIELD_NAMES,
    ProductKind,
    Provider,
    TicketingSettings,
)

MAP_HELP = "One per line: the provider's id, an equals sign, then {what}."


def parse_map(text, allowed, what):
    """``ID = value`` lines to a dict, refusing values outside ``allowed``.
    Blank lines and ``#`` comments are skipped."""
    result, errors = {}, []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, value = (part.strip() for part in line.partition("="))
        if not sep or not key or not value:
            errors.append(f"Line {number}: write it as ID = {what}.")
        elif value not in allowed:
            errors.append(f"Line {number}: {value!r} is not one of {what}.")
        else:
            result[key] = value
    if errors:
        raise forms.ValidationError(errors)
    return result


def parse_columns(text):
    """``field = Header`` lines: the field one of ours, the header free."""
    result, errors = {}, []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = (part.strip() for part in line.partition("="))
        if not sep or not key or not value:
            errors.append(f"Line {number}: write it as field = Column header.")
        elif key not in CSV_FIELD_NAMES:
            errors.append(
                f"Line {number}: {key!r} is not one of "
                + ", ".join(sorted(CSV_FIELD_NAMES))
                + "."
            )
        else:
            result[key] = value
    if errors:
        raise forms.ValidationError(errors)
    return result


def map_text(mapping):
    return "\n".join(f"{key} = {value}" for key, value in (mapping or {}).items())


class TicketingSettingsForm(forms.ModelForm):
    """The edition's Tickets page. The token and the webhook secret are
    write-only, like in the admin; the two maps are plain lines."""

    api_token = forms.CharField(
        label="API token",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current token.",
    )
    webhook_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current secret.",
    )
    question_lines = forms.CharField(
        label="Question map",
        required=False,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text=MAP_HELP.format(what="an attendee field: ")
        + ", ".join(sorted(ATTENDEE_FIELD_NAMES))
        + ". Questions not listed are kept with the registration, unmapped.",
    )
    csv_lines = forms.CharField(
        label="CSV columns",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One per line: our field, an equals sign, then the column header "
        "in the export. Fields: "
        + ", ".join(sorted(CSV_FIELD_NAMES))
        + ". Only email is required; with no status column everyone in the file "
        "counts as registered. For a CSV, the question map's ids are column headers.",
    )
    product_lines = forms.CharField(
        label="Product map",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=MAP_HELP.format(what="ticket or donation")
        + " Products not listed count as tickets.",
    )

    class Meta:
        model = TicketingSettings
        fields = [
            "provider",
            "base_url",
            "organizer",
            "event_id",
            "api_token",
            "webhook_secret",
            "anonymous_question",
            "anonymous_answer",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["question_lines"].initial = map_text(self.instance.question_map)
        self.fields["product_lines"].initial = map_text(self.instance.product_map)
        self.fields["csv_lines"].initial = map_text(self.instance.csv_columns)

    def _keep_when_blank(self, name):
        value = self.cleaned_data.get(name)
        return value if value else getattr(self.instance, name)

    def clean_api_token(self):
        return self._keep_when_blank("api_token")

    def clean_webhook_secret(self):
        return self._keep_when_blank("webhook_secret")

    def clean_question_lines(self):
        return parse_map(
            self.cleaned_data["question_lines"],
            ATTENDEE_FIELD_NAMES,
            "an attendee field",
        )

    def clean_product_lines(self):
        return parse_map(
            self.cleaned_data["product_lines"],
            set(ProductKind.values),
            "ticket or donation",
        )

    def clean_csv_lines(self):
        return parse_columns(self.cleaned_data["csv_lines"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("provider") == Provider.CSV and not (
            cleaned.get("csv_lines") or {}
        ).get("email"):
            self.add_error("csv_lines", "Name the email column: email = Email")
        if cleaned.get("provider") == Provider.PRETIX:
            for name in ("organizer", "event_id"):
                if not cleaned.get(name):
                    self.add_error(name, "Pretix needs this to find the orders.")
        return cleaned

    def save(self, commit=True):
        self.instance.question_map = self.cleaned_data["question_lines"]
        self.instance.product_map = self.cleaned_data["product_lines"]
        self.instance.csv_columns = self.cleaned_data["csv_lines"]
        return super().save(commit=commit)


class CsvImportForm(forms.Form):
    file = forms.FileField(
        label="CSV export",
        help_text="Comma-separated, UTF-8, one row per registration, headers on "
        "the first line.",
    )
