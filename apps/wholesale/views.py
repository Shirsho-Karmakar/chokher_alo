from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

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
