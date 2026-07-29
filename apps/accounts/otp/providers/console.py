import logging
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import BaseOTPProvider, OTPDeliveryResult


logger = logging.getLogger(__name__)


class ConsoleOTPProvider(BaseOTPProvider):
    """
    Development-only provider.

    It prints the OTP to the Django server terminal instead of sending SMS.
    """

    provider_name = "console"

    def send(
        self,
        *,
        phone_number: str,
        code: str,
        purpose: str,
    ) -> OTPDeliveryResult:
        if not settings.DEBUG:
            raise ImproperlyConfigured(
                "ConsoleOTPProvider cannot be used when DEBUG is False."
            )

        logger.warning(
            "DEVELOPMENT OTP for %s (%s): %s",
            phone_number,
            purpose,
            code,
        )

        return OTPDeliveryResult(
            message_id=f"console-{uuid.uuid4()}",
        )
