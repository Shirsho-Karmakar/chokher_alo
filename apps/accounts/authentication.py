import secrets

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.accounts.otp.phone import normalize_indian_phone_number


User = get_user_model()


class PublicPhoneLoginNotAllowed(Exception):
    """Raised when an account cannot use a public OTP login endpoint."""


def _validate_public_login_user(user) -> None:
    if not user.is_active:
        raise PublicPhoneLoginNotAllowed(
            "This account is not available."
        )

    # Staff and superuser accounts must continue using the protected
    # administration login rather than public customer OTP endpoints.
    if user.is_staff or user.is_superuser:
        raise PublicPhoneLoginNotAllowed(
            "Staff accounts cannot use this login method."
        )


def _mark_phone_verified(user) -> None:
    if not user.phone_verified:
        user.phone_verified = True
        user.save(update_fields=["phone_verified"])


@transaction.atomic
def get_or_create_phone_user(*, phone_number: str):
    """
    Find or create the shared customer identity for a verified phone number.

    The same user can later have both retail access and an approved
    wholesale profile.
    """
    normalized_phone = normalize_indian_phone_number(phone_number)

    user = (
        User.objects
        .select_for_update()
        .filter(phone_number=normalized_phone)
        .first()
    )

    if user is not None:
        _validate_public_login_user(user)
        _mark_phone_verified(user)
        return user, False

    base_username = f"phone_{normalized_phone.removeprefix('+')}"

    for attempt in range(5):
        username = (
            base_username
            if attempt == 0
            else f"{base_username}_{secrets.token_hex(4)}"
        )

        try:
            # The nested transaction creates a savepoint. This allows us to
            # recover safely from a concurrent unique-constraint conflict.
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    phone_number=normalized_phone,
                    phone_verified=True,
                )
        except IntegrityError:
            user = (
                User.objects
                .select_for_update()
                .filter(phone_number=normalized_phone)
                .first()
            )

            if user is not None:
                _validate_public_login_user(user)
                _mark_phone_verified(user)
                return user, False

            continue

        return user, True

    raise RuntimeError(
        "A unique user identity could not be created."
    )
