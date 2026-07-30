from django import forms

from apps.lenses.models import LensCoating

from .models import CustomerOwnedFrameService


class AddStandardItemForm(forms.Form):
    sku = forms.CharField(max_length=20)
    quantity = forms.IntegerField(
        min_value=1,
        max_value=10,
    )


class AddPoweredEyewearForm(forms.Form):
    sku = forms.CharField(max_length=20)
    prescription_id = forms.IntegerField(min_value=1)


class LensConfigurationForm(forms.Form):
    lens_id = forms.IntegerField(min_value=1)
    coating_ids = forms.ModelMultipleChoiceField(
        queryset=LensCoating.objects.none(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["coating_ids"].queryset = (
            LensCoating.objects
            .filter(is_active=True)
            .order_by("name")
        )


class AddCustomerOwnedFrameServiceForm(forms.Form):
    prescription_id = forms.IntegerField(min_value=1)
    completion_choice = forms.ChoiceField(
        choices=CustomerOwnedFrameService.CompletionChoice.choices,
    )
    frame_handling = forms.ChoiceField(
        choices=CustomerOwnedFrameService.FrameHandling.choices,
    )
    customer_notes = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea,
    )


class UpdateCartItemQuantityForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        max_value=10,
    )
