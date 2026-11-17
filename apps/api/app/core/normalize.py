"""Normalization of user-entered identifiers so lookups and uniqueness are exact."""

import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Iranian mobile numbers: 9xxxxxxxxx after the country/trunk prefix.
_IR_MOBILE_RE = re.compile(r"^9\d{9}$")


def to_ascii_digits(value: str) -> str:
    """Converts Persian and Arabic-Indic digits to ASCII."""
    return value.translate(_DIGITS)


def normalize_mobile(value: str) -> str | None:
    """Returns an Iranian mobile number as E.164 (``+989xxxxxxxxx``), or None if invalid.

    Accepts ``09…``, ``9…``, ``+989…`` and ``00989…`` with spaces, dashes and
    Persian digits.
    """
    digits = re.sub(r"[\s\-()]", "", to_ascii_digits(value))
    for prefix in ("+98", "0098", "98", "0"):
        if digits.startswith(prefix) and _IR_MOBILE_RE.match(digits[len(prefix) :]):
            return "+98" + digits[len(prefix) :]
    return "+98" + digits if _IR_MOBILE_RE.match(digits) else None


def normalize_email(value: str) -> str | None:
    """Returns a trimmed, lower-cased email address, or None if it is not plausibly valid."""
    email = value.strip().lower()
    return email if len(email) <= 254 and _EMAIL_RE.match(email) else None


def normalize_otp_code(value: str) -> str:
    """Keeps leading zeros and accepts Persian digits: «۰۱۲۳۴» → ``"01234"``."""
    return re.sub(r"\s", "", to_ascii_digits(value))
