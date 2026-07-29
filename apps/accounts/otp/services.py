import math
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import (
    ImproperlyConfigured,
    ValidationError as DjangoValidationError,
)
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.module_loading import import_string

from apps.accounts.models import (
    PhoneOTPChallenge,
    PhoneOTPThrottle,
)

from .exceptions import (
    OTPAlreadyUsed,
    OTPDeliveryError,
    OTPExpired,
    OTPInvalidCode,
    OTPNotReady,
    OTPResendTooSoon,
    OTPSendLimitExceeded,
    OTPTooManyAttempts,
)
from .phone import normalize_indian_phone_number
from .providers.base import BaseOTPProvider


OTP_HMAC_SALT = "chokher_alo.accounts.phone_otp"


def _positive_setting(name: str, *, allow_zero: bool = False) -> int:
    value = int(getattr(settings, name))
    minimum = 0 if allow_zero else 1

    if value < minimum:
        raise ImproperlyConfigured(
            f"{name} must be greater than or equal to {minimum}."
        )

    return value


def _validate_purpose(purpose: str) -> None:
    if purpose not in PhoneOTPChallenge.Purpose.values:
        raise ValueError(f"Unsupported OTP purpose: {purpose}")


def _generate_numeric_code(length: int) -> str:
    maximum = 10 ** length
    return str(secrets.randbelow(maximum)).zfill(length)


def _make_code_digest(
    *,
    challenge_id,
    phone_number: str,
    purpose: str,
    code: str,
) -> str:
    payload = (
        f"{challenge_id}:{phone_number}:{purpose}:{code}"
    )

    return salted_hmac(
        OTP_HMAC_SALT,
        payload,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def get_otp_provider() -> BaseOTPProvider:
    provider_class = import_string(settings.PHONE_OTP_PROVIDER)
    provider = provider_class()

    if not isinstance(provider, BaseOTPProvider):
        raise ImproperlyConfigured(
            "PHONE_OTP_PROVIDER must inherit from BaseOTPProvider."
        )

    return provider


def issue_phone_otp(
    *,
    phone_number: str,
    purpose: str,
) -> PhoneOTPChallenge:
    normalized_phone = normalize_indian_phone_number(phone_number)
    _validate_purpose(purpose)

    code_length = _positive_setting("PHONE_OTP_CODE_LENGTH")
    ttl_seconds = _positive_setting("PHONE_OTP_TTL_SECONDS")
    resend_seconds = _positive_setting(
        "PHONE_OTP_RESEND_SECONDS",
        allow_zero=True,
    )
    max_sends_per_hour = _positive_setting(
        "PHONE_OTP_MAX_SENDS_PER_HOUR"
    )
    max_attempts = _positive_setting(
        "PHONE_OTP_MAX_ATTEMPTS"
    )

    provider = get_otp_provider()
    now = timezone.now()

    with transaction.atomic():
        throttle, _ = PhoneOTPThrottle.objects.get_or_create(
            phone_number=normalized_phone,
            purpose=purpose,
        )

        throttle = (
            PhoneOTPThrottle.objects
            .select_for_update()
            .get(pk=throttle.pk)
        )

        if throttle.last_sent_at is not None:
            elapsed_seconds = (
                now - throttle.last_sent_at
            ).total_seconds()

            if elapsed_seconds < resend_seconds:
                retry_after = math.ceil(
                    resend_seconds - elapsed_seconds
                )
                raise OTPResendTooSoon(retry_after)

        window_expired = (
            throttle.window_started_at is None
            or now
            >= throttle.window_started_at + timedelta(hours=1)
        )

        if window_expired:
            throttle.window_started_at = now
            throttle.sends_in_window = 0

        if throttle.sends_in_window >= max_sends_per_hour:
            raise OTPSendLimitExceeded(
                "The hourly OTP send limit has been reached."
            )

        # Only the newest OTP for this phone and purpose can remain valid.
        (
            PhoneOTPChallenge.objects
            .filter(
                phone_number=normalized_phone,
                purpose=purpose,
                consumed_at__isnull=True,
                invalidated_at__isnull=True,
            )
            .update(invalidated_at=now)
        )

        challenge_id = uuid.uuid4()
        code = _generate_numeric_code(code_length)

        challenge = PhoneOTPChallenge.objects.create(
            id=challenge_id,
            phone_number=normalized_phone,
            purpose=purpose,
            code_digest=_make_code_digest(
                challenge_id=challenge_id,
                phone_number=normalized_phone,
                purpose=purpose,
                code=code,
            ),
            max_attempts=max_attempts,
            provider_name=provider.provider_name,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )

        throttle.last_sent_at = now
        throttle.sends_in_window += 1
        throttle.save(
            update_fields=[
                "window_started_at",
                "sends_in_window",
                "last_sent_at",
                "updated_at",
            ]
        )

    try:
        delivery_result = provider.send(
            phone_number=normalized_phone,
            code=code,
            purpose=purpose,
        )
    except Exception as exc:
        PhoneOTPChallenge.objects.filter(
            pk=challenge.pk
        ).update(
            invalidated_at=timezone.now()
        )

        raise OTPDeliveryError(
            "The OTP could not be delivered."
        ) from exc

    challenge.sent_at = timezone.now()
    challenge.provider_message_id = delivery_result.message_id
    challenge.save(
        update_fields=[
            "sent_at",
            "provider_message_id",
        ]
    )

    return challenge


def verify_phone_otp(
    *,
    challenge_id,
    code: str,
) -> PhoneOTPChallenge:
    now = timezone.now()
    deferred_error = None
    verified_challenge = None

    try:
        with transaction.atomic():
            challenge = (
                PhoneOTPChallenge.objects
                .select_for_update()
                .get(pk=challenge_id)
            )

            if challenge.consumed_at is not None:
                deferred_error = OTPAlreadyUsed(
                    "This OTP has already been used."
                )

            elif challenge.invalidated_at is not None:
                deferred_error = OTPInvalidCode()

            elif challenge.sent_at is None:
                deferred_error = OTPNotReady(
                    "The OTP has not been delivered."
                )

            elif challenge.expires_at <= now:
                challenge.invalidated_at = now
                challenge.save(
                    update_fields=["invalidated_at"]
                )
                deferred_error = OTPExpired(
                    "The OTP has expired."
                )

            elif challenge.attempt_count >= challenge.max_attempts:
                if challenge.invalidated_at is None:
                    challenge.invalidated_at = now
                    challenge.save(
                        update_fields=["invalidated_at"]
                    )

                deferred_error = OTPTooManyAttempts(
                    "The maximum verification attempts were exceeded."
                )

            else:
                candidate_code = str(code).strip()

                candidate_digest = _make_code_digest(
                    challenge_id=challenge.id,
                    phone_number=challenge.phone_number,
                    purpose=challenge.purpose,
                    code=candidate_code,
                )

                digest_matches = constant_time_compare(
                    challenge.code_digest,
                    candidate_digest,
                )

                code_has_valid_format = (
                    candidate_code.isdigit()
                    and len(candidate_code)
                    == settings.PHONE_OTP_CODE_LENGTH
                )

                if digest_matches and code_has_valid_format:
                    challenge.consumed_at = now
                    challenge.save(
                        update_fields=["consumed_at"]
                    )
                    verified_challenge = challenge
                else:
                    challenge.attempt_count += 1

                    update_fields = ["attempt_count"]
                    remaining_attempts = (
                        challenge.max_attempts
                        - challenge.attempt_count
                    )

                    if remaining_attempts <= 0:
                        challenge.invalidated_at = now
                        update_fields.append("invalidated_at")

                        deferred_error = OTPTooManyAttempts(
                            "The maximum verification attempts "
                            "were exceeded."
                        )
                    else:
                        deferred_error = OTPInvalidCode(
                            remaining_attempts=remaining_attempts
                        )

                    challenge.save(update_fields=update_fields)

    except (
        PhoneOTPChallenge.DoesNotExist,
        DjangoValidationError,
        ValueError,
    ) as exc:
        raise OTPInvalidCode() from exc

    if deferred_error is not None:
        raise deferred_error

    if verified_challenge is None:
        raise OTPInvalidCode()

    return verified_challenge
