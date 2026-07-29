class OTPError(Exception):
    """Base exception for phone OTP operations."""


class InvalidPhoneNumber(OTPError):
    pass


class OTPResendTooSoon(OTPError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Please wait {retry_after_seconds} seconds before requesting "
            "another OTP."
        )


class OTPSendLimitExceeded(OTPError):
    pass


class OTPDeliveryError(OTPError):
    pass


class OTPInvalidCode(OTPError):
    def __init__(self, remaining_attempts: int | None = None):
        self.remaining_attempts = remaining_attempts
        super().__init__("The OTP is invalid.")


class OTPExpired(OTPError):
    pass


class OTPAlreadyUsed(OTPError):
    pass


class OTPTooManyAttempts(OTPError):
    pass


class OTPNotReady(OTPError):
    pass
