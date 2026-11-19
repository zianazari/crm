"""Gregorian to Solar Hijri dates for text the API writes itself (SMS and email); the
web app formats dates on its own."""

from datetime import date, datetime

MONTHS = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)
# date.weekday(): Monday is 0.
WEEKDAYS = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه")

_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def to_jalali(day: date) -> tuple[int, int, int]:
    gy, gm, gd = day.year, day.month, day.day
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + 365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        + gd
        + _DAYS_BEFORE_MONTH[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def long_date(day: date) -> str:
    """For example «پنجشنبه ۲۸ آبان ۱۴۰۵»."""
    jy, jm, jd = to_jalali(day)
    digits = str(jd).translate(_DIGITS), str(jy).translate(_DIGITS)
    return f"{WEEKDAYS[day.weekday()]} {digits[0]} {MONTHS[jm - 1]} {digits[1]}"


def long_datetime(moment: datetime) -> str:
    """A local (already converted) moment: «پنجشنبه ۲۸ آبان ۱۴۰۵ ساعت ۱۰:۳۰»."""
    return f"{long_date(moment.date())} ساعت {moment.strftime('%H:%M').translate(_DIGITS)}"
