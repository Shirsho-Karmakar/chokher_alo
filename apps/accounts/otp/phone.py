import re

from .exceptions import InvalidPhoneNumber


ALLOWED_PHONE_CHARACTERS = re.compile(r"^[0-9+\s()\-]+$")
INDIAN_MOBILE_NUMBER = re.compile(r"^[6-9][0-9]{9}$")


def normalize_indian_phone_number(value: str) -> str:
    """
    Normalize common Indian mobile-number formats to E.164-style +91 format.

    Accepted examples:
        9876543210
        09876543210
        919876543210
        +91 98765 43210
    """

    if value is None:
        raise InvalidPhoneNumber("A phone number is required.")

    raw_value = str(value).strip()

    if not raw_value:
        raise InvalidPhoneNumber("A phone number is required.")

    if not ALLOWED_PHONE_CHARACTERS.fullmatch(raw_value):
        raise InvalidPhoneNumber(
            "The phone number contains invalid characters."
        )

    if raw_value.count("+") > 1:
        raise InvalidPhoneNumber("The phone number is invalid.")

    if "+" in raw_value and not raw_value.startswith("+"):
        raise InvalidPhoneNumber("The phone number is invalid.")

    digits = re.sub(r"\D", "", raw_value)

    if len(digits) == 10:
        national_number = digits
    elif len(digits) == 11 and digits.startswith("0"):
        national_number = digits[1:]
    elif len(digits) == 12 and digits.startswith("91"):
        national_number = digits[2:]
    else:
        raise InvalidPhoneNumber(
            "Enter a valid Indian mobile number."
        )

    if not INDIAN_MOBILE_NUMBER.fullmatch(national_number):
        raise InvalidPhoneNumber(
            "Enter a valid Indian mobile number."
        )

    return f"+91{national_number}"
