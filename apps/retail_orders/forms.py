from django import forms

from .models import RetailOrder


class RetailCheckoutForm(forms.Form):
    fulfillment_method = forms.ChoiceField(
        choices=RetailOrder.FulfillmentMethod.choices,
    )
    payment_method = forms.ChoiceField(
        choices=RetailOrder.PaymentMethod.choices,
    )

    shipping_address_id = forms.IntegerField(
        required=False,
        min_value=1,
    )
    billing_address_id = forms.IntegerField(
        required=False,
        min_value=1,
    )
    billing_same_as_shipping = forms.BooleanField(
        required=False,
    )

    customer_notes = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea,
    )


class RazorpaySuccessForm(forms.Form):
    razorpay_order_id = forms.CharField(
        max_length=150,
    )
    razorpay_payment_id = forms.CharField(
        max_length=150,
    )
    razorpay_signature = forms.CharField(
        max_length=500,
    )


class RetailOrderCancellationForm(forms.Form):
    reason = forms.CharField(
        max_length=1000,
        strip=True,
    )


class RetailOrderListForm(forms.Form):
    page = forms.IntegerField(
        required=False,
        min_value=1,
    )
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=50,
    )


class StaffRetailOrderListForm(forms.Form):
    status = forms.ChoiceField(
        choices=RetailOrder.Status.choices,
        required=False,
    )
    payment_status = forms.ChoiceField(
        choices=RetailOrder.PaymentStatus.choices,
        required=False,
    )
    fulfillment_method = forms.ChoiceField(
        choices=RetailOrder.FulfillmentMethod.choices,
        required=False,
    )
    q = forms.CharField(
        required=False,
        max_length=150,
        strip=True,
    )
    page = forms.IntegerField(
        required=False,
        min_value=1,
    )
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
    )


class StaffOrderNoteForm(forms.Form):
    note = forms.CharField(
        required=False,
        max_length=1000,
        strip=True,
        widget=forms.Textarea,
    )


class StaffShipmentForm(StaffOrderNoteForm):
    carrier_name = forms.CharField(
        max_length=100,
        strip=True,
    )
    tracking_number = forms.CharField(
        max_length=150,
        strip=True,
    )


class StaffPayAtStorePaymentForm(StaffOrderNoteForm):
    receipt_reference = forms.CharField(
        required=False,
        max_length=150,
        strip=True,
    )


class StaffCustomerFrameReceivedForm(StaffOrderNoteForm):
    pass
