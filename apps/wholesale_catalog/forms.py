from django import forms

from apps.prescriptions.models import PrescriptionEyeValue


class WholesaleCatalogueQueryForm(forms.Form):
    prescription_id = forms.IntegerField(
        min_value=1,
    )


class WholesaleBoxQuoteForm(forms.Form):
    prescription_id = forms.IntegerField(
        min_value=1,
    )
    variant_id = forms.IntegerField(
        min_value=1,
    )
    eye = forms.ChoiceField(
        choices=PrescriptionEyeValue.Eye.choices,
    )
    boxes = forms.IntegerField(
        min_value=1,
    )
