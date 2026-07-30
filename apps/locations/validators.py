import re

from django.core.exceptions import ValidationError


INDIAN_PIN_CODE_PATTERN = re.compile(r"^[1-9][0-9]{5}$")


def normalize_indian_pin_code(value: str) -> str:
    """
    Normalize and structurally validate a six-digit Indian PIN code.

    This validates format only. Actual delivery availability is determined
    by the ServiceablePincode records maintained by staff.
    """
    if value is None:
        raise ValidationError("A PIN code is required.")

    normalized_value = str(value).strip()

    if not INDIAN_PIN_CODE_PATTERN.fullmatch(normalized_value):
        raise ValidationError(
            "Enter a valid six-digit Indian PIN code."
        )

    return normalized_value
