from django import forms

from .models import Prescription, PrescriptionEyeValue


class PrescriptionUploadForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = (
            "prescription_file",
            "customer_notes",
        )


class PrescriptionEyeValueForm(forms.Form):
    sphere = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
    )
    cylinder = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
    )
    axis = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=180,
    )
    add_power = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
    )

    distance_pd_mm = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=0,
    )
    near_pd_mm = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=0,
    )

    prism_diopters = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=0,
    )
    prism_base = forms.ChoiceField(
        required=False,
        choices=(
            ("", "---------"),
            *PrescriptionEyeValue.PrismBase.choices,
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        cylinder = cleaned_data.get("cylinder")
        axis = cleaned_data.get("axis")
        prism_diopters = cleaned_data.get("prism_diopters")
        prism_base = cleaned_data.get("prism_base")

        if axis is not None and cylinder is None:
            self.add_error(
                "axis",
                "Cylinder must be entered when an axis is provided.",
            )

        if prism_diopters is not None and not prism_base:
            self.add_error(
                "prism_base",
                "Select a prism base when prism power is entered.",
            )

        if prism_base and prism_diopters is None:
            self.add_error(
                "prism_diopters",
                "Enter prism power when a prism base is selected.",
            )

        return cleaned_data

    @property
    def has_written_values(self) -> bool:
        if not hasattr(self, "cleaned_data"):
            return False

        return any(
            value not in (None, "")
            for value in self.cleaned_data.values()
        )
