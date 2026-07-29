from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class OTPDeliveryResult:
    message_id: str = ""


class BaseOTPProvider(ABC):
    provider_name = "base"

    @abstractmethod
    def send(
        self,
        *,
        phone_number: str,
        code: str,
        purpose: str,
    ) -> OTPDeliveryResult:
        """
        Deliver an OTP and return the provider's message identifier.
        """
        raise NotImplementedError
