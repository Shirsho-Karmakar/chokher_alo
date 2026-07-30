from django import forms

from .models import LensCoating


class CompatibleLensQueryForm(forms.Form):
    prescription_id = forms.IntegerField(
        min_value=1,
    )


class LensQuoteRequestForm(forms.Form):
    prescription_id = forms.IntegerField(
        min_value=1,
    )
    lens_id = forms.IntegerField(
        min_value=1,
    )
    coating_ids = forms.ModelMultipleChoiceField(
        queryset=LensCoating.objects.none(),
        required=False,
    )
    frame_variant_id = forms.IntegerField(
        required=False,
        min_value=1,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["coating_ids"].queryset = (
            LensCoating.objects
            .filter(is_active=True)
            .order_by("name")
        )
