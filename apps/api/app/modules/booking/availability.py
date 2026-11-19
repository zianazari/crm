"""Free time in one person's calendar (spec 4.10).

A slot is free when it lies inside that day's working hours, the day is not a holiday
or the person's leave, it is at least the minimum notice from now and within the
booking horizon, and the meeting with its buffers overlaps no open timed activity and
no confirmed booking. Activities without a time (a task with only a due date) never
block. Only the CRM's own calendar is consulted until an outside calendar is connected.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.activities.models import OPEN_STATUSES, Activity
from app.modules.activities.service import DEFAULT_DURATION
from app.modules.booking.models import (
    AvailabilityException,
    AvailabilityRule,
    Booking,
    BookingSettings,
    BookingStatus,
    MeetingType,
)

STEP_MINUTES = 30  # slots start on the hour and half hour of the working period

# Defaults until the organization decides (open question 14, recorded in spec 0.1).
DEFAULT_HOURS: dict[int, tuple[time, time]] = {
    **{weekday: (time(9), time(17)) for weekday in range(5)},  # Saturday to Wednesday
    5: (time(9), time(13)),  # Thursday
}
DEFAULT_MEETING = ("جلسه مشاوره", 30)


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def weekday_of(day: date) -> int:
    """0 for Saturday ... 6 for Friday."""
    return (day.weekday() + 2) % 7


def ensure_settings(db: Session, user_id: uuid.UUID) -> BookingSettings:
    """The person's settings, created with the defaults (hours and one meeting type) the
    first time anyone looks."""
    row = db.get(BookingSettings, user_id)
    if row is not None:
        return row
    row = BookingSettings(
        user_id=user_id,
        buffer_before_minutes=0,
        buffer_after_minutes=10,
        min_notice_minutes=240,
        horizon_days=30,
        change_deadline_hours=24,
    )
    db.add(row)
    for weekday, (start, end) in DEFAULT_HOURS.items():
        db.add(AvailabilityRule(user_id=user_id, weekday=weekday, start_time=start, end_time=end))
    if db.scalar(select(MeetingType.id).where(MeetingType.user_id == user_id).limit(1)) is None:
        db.add(
            MeetingType(
                user_id=user_id, title=DEFAULT_MEETING[0], duration_minutes=DEFAULT_MEETING[1]
            )
        )
    db.flush()
    return row


@dataclass(frozen=True)
class Calendar:
    settings: BookingSettings
    rules: list[AvailabilityRule]
    days_off: set[date]
    busy: list[tuple[datetime, datetime]]
    start: datetime  # earliest bookable moment
    last_day: date


def _days_off(db: Session, user_id: uuid.UUID, first: date, last: date) -> set[date]:
    rows = db.scalars(
        select(AvailabilityException).where(
            or_(AvailabilityException.user_id == user_id, AvailabilityException.user_id.is_(None)),
            AvailabilityException.start_date <= last,
            AvailabilityException.end_date >= first,
        )
    )
    off: set[date] = set()
    for row in rows:
        day = max(row.start_date, first)
        while day <= min(row.end_date, last):
            off.add(day)
            day += timedelta(days=1)
    return off


def _busy(
    db: Session,
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
    ignore_booking: Booking | None,
) -> list[tuple[datetime, datetime]]:
    ignore_activity = ignore_booking.activity_id if ignore_booking else None
    activities = db.execute(
        select(Activity.id, Activity.start_at, Activity.duration_minutes).where(
            Activity.owner_id == user_id,
            Activity.status.in_(OPEN_STATUSES),
            Activity.start_at.is_not(None),
            Activity.start_at < end,
            Activity.start_at >= start - timedelta(days=1),
        )
    ).all()
    busy: list[tuple[datetime, datetime]] = [
        (begin, begin + timedelta(minutes=minutes or DEFAULT_DURATION))
        for activity_id, begin, minutes in activities
        if activity_id != ignore_activity and begin is not None
    ]
    bookings = db.execute(
        select(Booking.id, Booking.start_at, Booking.end_at).where(
            Booking.user_id == user_id,
            Booking.status == BookingStatus.CONFIRMED,
            Booking.start_at < end,
            Booking.end_at > start,
        )
    ).all()
    busy += [
        (begin, finish)
        for booking_id, begin, finish in bookings
        if ignore_booking is None or booking_id != ignore_booking.id
    ]
    return sorted(busy)


def load(
    db: Session,
    user_id: uuid.UUID,
    now: datetime | None = None,
    *,
    ignore_booking: Booking | None = None,
) -> Calendar:
    now = now or datetime.now(UTC)
    settings = ensure_settings(db, user_id)
    zone = tz()
    first = now.astimezone(zone).date()
    last = first + timedelta(days=settings.horizon_days)
    rules = list(
        db.scalars(
            select(AvailabilityRule)
            .where(AvailabilityRule.user_id == user_id)
            .order_by(AvailabilityRule.weekday, AvailabilityRule.start_time)
        )
    )
    window_end = datetime.combine(last + timedelta(days=1), time(), zone)
    return Calendar(
        settings=settings,
        rules=rules,
        days_off=_days_off(db, user_id, first, last),
        busy=_busy(db, user_id, now, window_end, ignore_booking),
        start=now + timedelta(minutes=settings.min_notice_minutes),
        last_day=last,
    )


def _overlaps(begin: datetime, end: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    return any(b < end and begin < e for b, e in busy)


def slots(calendar: Calendar, meeting: MeetingType) -> Iterator[datetime]:
    """Free start times (UTC), in order."""
    zone = tz()
    length = timedelta(minutes=meeting.duration_minutes)
    before = timedelta(minutes=calendar.settings.buffer_before_minutes)
    after = timedelta(minutes=calendar.settings.buffer_after_minutes)
    step = timedelta(minutes=STEP_MINUTES)
    day = calendar.start.astimezone(zone).date()
    while day <= calendar.last_day:
        if day not in calendar.days_off:
            for rule in calendar.rules:
                if rule.weekday != weekday_of(day):
                    continue
                moment = datetime.combine(day, rule.start_time, zone)
                close = datetime.combine(day, rule.end_time, zone)
                while moment + length <= close:
                    if moment >= calendar.start and not _overlaps(
                        moment - before, moment + length + after, calendar.busy
                    ):
                        yield moment.astimezone(UTC)
                    moment += step
        day += timedelta(days=1)


def is_free(calendar: Calendar, meeting: MeetingType, start_at: datetime) -> bool:
    wanted = start_at.astimezone(UTC)
    return any(slot == wanted for slot in slots(calendar, meeting))
