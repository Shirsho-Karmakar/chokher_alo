from django import forms

from .models import WholesaleOrder, WholesalePaymentAttempt


WHOLESALE_PAYMENT_METHOD_CHOICES = (
    (
        WholesalePaymentAttempt.Method.RAZORPAY,
        "Online payment",
    ),
    (
        WholesalePaymentAttempt.Method.BANK_TRANSFER,
        "Bank transfer",
    ),
)


class WholesaleCheckoutForm(forms.Form):
    payment_method = forms.ChoiceField(
        choices=WHOLESALE_PAYMENT_METHOD_CHOICES,
    )
    customer_notes = forms.CharField(
        required=False,
        max_length=2000,
        strip=True,
        widget=forms.Textarea,
    )


class WholesaleRazorpaySuccessForm(forms.Form):
    razorpay_order_id = forms.CharField(max_length=150)
    razorpay_payment_id = forms.CharField(max_length=150)
    razorpay_signature = forms.CharField(max_length=500)


class WholesaleOrderCancellationForm(forms.Form):
    reason = forms.CharField(
        max_length=1000,
        strip=True,
    )


class WholesaleOrderListForm(forms.Form):
    page = forms.IntegerField(
        required=False,
        min_value=1,
    )
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=50,
    )


class StaffWholesaleOrderListForm(forms.Form):
    status = forms.ChoiceField(
        choices=WholesaleOrder.Status.choices,
        required=False,
    )
    payment_status = forms.ChoiceField(
        choices=WholesaleOrder.PaymentStatus.choices,
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


class StaffBankTransferConfirmationForm(forms.Form):
    transfer_reference = forms.CharField(
        max_length=150,
        strip=True,
    )
    note = forms.CharField(
        required=False,
        max_length=1000,
        strip=True,
    )


class StaffWholesaleOrderNoteForm(forms.Form):
    note = forms.CharField(
        required=False,
        max_length=1000,
        strip=True,
    )


class StaffWholesaleShipmentForm(
    StaffWholesaleOrderNoteForm
):
    carrier_name = forms.CharField(
        max_length=100,
        strip=True,
    )
    tracking_number = forms.CharField(
        max_length=150,
        strip=True,
    )
