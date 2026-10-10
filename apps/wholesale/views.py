from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from .models import (
    WholesaleAccount,
    WholesaleVerificationContact,
)
from .permissions import approved_wholesale_required


@require_GET
def login_information(request):
    return JsonResponse(
        {
            "message": "Wholesale login uses phone OTP.",
            "request_otp_url": (
                "/wholesale/auth/phone/request/"
            ),
            "verify_otp_url": (
                "/wholesale/auth/phone/verify/"
            ),
        }
    )


@login_required(login_url=settings.WHOLESALE_LOGIN_URL)
@require_GET
def status(request):
    try:
        account = request.user.wholesale_account
    except WholesaleAccount.DoesNotExist:
        return JsonResponse(
            {
                "ok": False,
                "error": {
                    "code": "wholesale_account_not_created",
                    "message": (
                        "Use the wholesale phone login to create "
                        "a wholesale reference ID."
                    ),
                },
            },
            status=404,
        )

    contacts = list(
        WholesaleVerificationContact.objects
        .filter(is_active=True)
        .order_by("display_order", "created_at")
        .values(
            "label",
            "phone_number",
        )
    )

    return JsonResponse(
        {
            "ok": True,
            "reference_id": account.reference_id,
            "status": account.status,
            "status_label": account.get_status_display(),
            "business_name": account.business_name,
            "verification": {
                "instructions": (
                    "Call one of the verification numbers and "
                    "provide your wholesale reference ID."
                ),
                "contacts": contacts,
            },
        }
    )


@approved_wholesale_required
@require_GET
def dashboard(request):
    account = request.user.wholesale_account

    return JsonResponse(
        {
            "ok": True,
            "message": "Wholesale access approved.",
            "reference_id": account.reference_id,
        }
    )


@login_required(login_url=settings.WHOLESALE_LOGIN_URL)
@require_http_methods(["GET", "POST"])
def profile(request):
    try:
        account = request.user.wholesale_account
    except WholesaleAccount.DoesNotExist:
        return JsonResponse({
            "ok": False,
            "error": {
                "code": "wholesale_account_not_created",
                "message": "Use wholesale phone login first.",
            },
        }, status=404)

    if request.method == "POST":
        account.business_name = request.POST.get("business_name", account.business_name).strip()
        account.contact_person_name = request.POST.get("contact_person_name", account.contact_person_name).strip()
        account.gstin = request.POST.get("gstin", account.gstin).strip().upper()
        account.invoice_email = request.POST.get("invoice_email", account.invoice_email).strip()
        try:
            account.full_clean()
            account.save(update_fields=[
                "business_name",
                "contact_person_name",
                "gstin",
                "invoice_email",
                "updated_at",
            ])
        except ValidationError as exc:
            fields = exc.message_dict if hasattr(exc, "message_dict") else {"__all__": exc.messages}
            return JsonResponse({
                "ok": False,
                "error": {
                    "code": "invalid_wholesale_profile",
                    "message": "Correct the business details and try again.",
                    "fields": fields,
                },
            }, status=400)

    return JsonResponse({
        "ok": True,
        "profile": {
            "reference_id": account.reference_id,
            "status": account.status,
            "status_label": account.get_status_display(),
            "business_name": account.business_name,
            "contact_person_name": account.contact_person_name,
            "gstin": account.gstin,
            "invoice_email": account.invoice_email,
            "missing_checkout_details": list(account.missing_checkout_details()),
            "business_details_complete": account.business_details_complete,
            "is_checkout_ready": account.is_checkout_ready,
        },
    })
