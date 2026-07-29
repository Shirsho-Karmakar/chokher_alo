from django.conf import settings
from django.contrib.auth import login
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.authentication import (
    PublicPhoneLoginNotAllowed,
    get_or_create_phone_user,
)
from apps.accounts.models import PhoneOTPChallenge
from apps.accounts.otp.exceptions import (
    InvalidPhoneNumber,
    OTPAlreadyUsed,
    OTPDeliveryError,
    OTPExpired,
    OTPInvalidCode,
    OTPNotReady,
    OTPResendTooSoon,
    OTPSendLimitExceeded,
    OTPTooManyAttempts,
)
from apps.accounts.otp.services import (
    issue_phone_otp,
    verify_phone_otp,
)
from apps.wholesale.models import WholesaleAccount


DJANGO_MODEL_BACKEND = (
    "django.contrib.auth.backends.ModelBackend"
)


def _error_response(
    *,
    code: str,
    message: str,
    status: int,
    **extra,
) -> JsonResponse:
    payload = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }

    payload["error"].update(extra)

    return JsonResponse(payload, status=status)


def _request_otp(request, *, purpose: str) -> JsonResponse:
    try:
        challenge = issue_phone_otp(
            phone_number=request.POST.get("phone_number"),
            purpose=purpose,
        )
    except InvalidPhoneNumber as exc:
        return _error_response(
            code="invalid_phone_number",
            message=str(exc),
            status=400,
        )
    except OTPResendTooSoon as exc:
        return _error_response(
            code="otp_resend_too_soon",
            message=str(exc),
            status=429,
            retry_after_seconds=exc.retry_after_seconds,
        )
    except OTPSendLimitExceeded as exc:
        return _error_response(
            code="otp_send_limit_exceeded",
            message=str(exc),
            status=429,
        )
    except OTPDeliveryError:
        return _error_response(
            code="otp_delivery_failed",
            message=(
                "The OTP could not be sent. "
                "Please try again later."
            ),
            status=503,
        )

    return JsonResponse(
        {
            "ok": True,
            "challenge_id": str(challenge.id),
            "expires_in_seconds": settings.PHONE_OTP_TTL_SECONDS,
            "resend_after_seconds": (
                settings.PHONE_OTP_RESEND_SECONDS
            ),
        },
        status=201,
    )


def _verify_otp(
    request,
    *,
    purpose: str,
    create_wholesale_account: bool,
) -> JsonResponse:
    try:
        challenge = verify_phone_otp(
            challenge_id=request.POST.get("challenge_id"),
            code=request.POST.get("code", ""),
            expected_purpose=purpose,
        )
    except OTPInvalidCode as exc:
        extra = {}

        if exc.remaining_attempts is not None:
            extra["remaining_attempts"] = exc.remaining_attempts

        return _error_response(
            code="invalid_otp",
            message="The OTP is invalid.",
            status=400,
            **extra,
        )
    except OTPExpired:
        return _error_response(
            code="otp_expired",
            message="The OTP has expired.",
            status=410,
        )
    except OTPAlreadyUsed:
        return _error_response(
            code="otp_already_used",
            message="This OTP has already been used.",
            status=409,
        )
    except OTPTooManyAttempts:
        return _error_response(
            code="otp_attempt_limit_exceeded",
            message=(
                "Too many incorrect attempts. "
                "Request a new OTP."
            ),
            status=429,
        )
    except OTPNotReady:
        return _error_response(
            code="otp_not_ready",
            message="The OTP is not ready for verification.",
            status=409,
        )

    try:
        user, user_created = get_or_create_phone_user(
            phone_number=challenge.phone_number,
        )
    except PublicPhoneLoginNotAllowed as exc:
        return _error_response(
            code="phone_login_not_allowed",
            message=str(exc),
            status=403,
        )

    login(
        request,
        user,
        backend=DJANGO_MODEL_BACKEND,
    )

    response_data = {
        "ok": True,
        "user_created": user_created,
        "phone_number": user.phone_number,
    }

    if not create_wholesale_account:
        response_data["redirect_url"] = "/"
        return JsonResponse(response_data)

    wholesale_account, wholesale_created = (
        WholesaleAccount.objects.get_or_create(user=user)
    )

    if wholesale_account.is_approved:
        redirect_url = reverse("wholesale:dashboard")
    else:
        redirect_url = reverse("wholesale:status")

    response_data.update(
        {
            "redirect_url": redirect_url,
            "wholesale": {
                "created": wholesale_created,
                "reference_id": wholesale_account.reference_id,
                "status": wholesale_account.status,
            },
        }
    )

    return JsonResponse(response_data)


@require_POST
def request_retail_phone_otp(request):
    return _request_otp(
        request,
        purpose=PhoneOTPChallenge.Purpose.RETAIL_LOGIN,
    )


@require_POST
def verify_retail_phone_otp(request):
    return _verify_otp(
        request,
        purpose=PhoneOTPChallenge.Purpose.RETAIL_LOGIN,
        create_wholesale_account=False,
    )


@require_POST
def request_wholesale_phone_otp(request):
    return _request_otp(
        request,
        purpose=PhoneOTPChallenge.Purpose.WHOLESALE_LOGIN,
    )


@require_POST
def verify_wholesale_phone_otp(request):
    return _verify_otp(
        request,
        purpose=PhoneOTPChallenge.Purpose.WHOLESALE_LOGIN,
        create_wholesale_account=True,
    )
