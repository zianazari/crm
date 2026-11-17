import pytest

from app.core.normalize import normalize_email, normalize_mobile, normalize_otp_code


@pytest.mark.parametrize(
    "raw",
    [
        "09121234567",
        "9121234567",
        "+989121234567",
        "00989121234567",
        "۰۹۱۲ ۱۲۳ ۴۵۶۷",
        "0912-123-4567",
    ],
)
def test_mobile_forms_normalize_to_e164(raw: str) -> None:
    assert normalize_mobile(raw) == "+989121234567"


@pytest.mark.parametrize("raw", ["0212345678", "12345", "091212345678", "abc"])
def test_invalid_mobiles(raw: str) -> None:
    assert normalize_mobile(raw) is None


def test_email_is_trimmed_and_lowercased() -> None:
    assert normalize_email("  Sara@Example.COM ") == "sara@example.com"
    assert normalize_email("not-an-email") is None


def test_otp_code_keeps_leading_zero_and_accepts_persian_digits() -> None:
    assert normalize_otp_code("۰۱۲۳۴") == "01234"
    assert normalize_otp_code(" 00042 ") == "00042"
