"""Booking, moving and canceling a meeting (spec 4.10; criterion 18).

Every change takes a transaction-scoped advisory lock on the calendar owner, checks
the wanted time against free time again, and only then writes the booking and its
meeting activity. Two customers asking for the same slot at once queue on the lock; the
second finds the slot taken and gets fresh free times. The bookings exclusion
constraint backs this up at the row level.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.jalali import long_datetime
from app.modules.activities.models import (
    OPEN_STATUSES,
    Activity,
    ActivityEvent,
    ActivityStatus,
    ActivityType,
)
from app.modules.activities.service import refresh_reminder, schedule_snapshot
from app.modules.booking import availability
from app.modules.booking.models import Booking, BookingLink, BookingStatus
from app.modules.messaging.models import Channel, Purpose
from app.modules.messaging.service import enqueue
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import notify

LINK_STAFF_REMINDER_MINUTES = 30
CUSTOMER_REMINDER_HOURS = 24
# A booking made later than this before the meeting gets no separate reminder.
CUSTOMER_REMINDER_MIN_LEAD = timedelta(hours=6)

LinkState = Literal["open", "booked", "expired", "revoked"]


class SlotTakenError(Exception):
    """The wanted time is no longer free."""


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link_url(token: str) -> str:
    return f"{get_settings().public_web_url.rstrip('/')}/book/{token}"


def active_booking(db: Session, link: BookingLink) -> Booking | None:
    return db.scalar(
        select(Booking).where(Booking.link_id == link.id, Booking.status == BookingStatus.CONFIRMED)
    )


def link_state(db: Session, link: BookingLink, now: datetime | None = None) -> LinkState:
    now = now or datetime.now(UTC)
    if link.revoked_at is not None:
        return "revoked"
    if active_booking(db, link) is not None:
        return "booked"
    if link.expires_at <= now or link.customer.archived_at is not None or not link.user.is_active:
        return "expired"
    return "open"


def change_deadline(db: Session, booking: Booking) -> datetime:
    settings = availability.ensure_settings(db, booking.user_id)
    return booking.start_at - timedelta(hours=settings.change_deadline_hours)


def can_change(db: Session, booking: Booking, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return booking.status is BookingStatus.CONFIRMED and now < change_deadline(db, booking)


def lock_calendar(db: Session, user_id: uuid.UUID) -> None:
    key = int.from_bytes(user_id.bytes[:8], "big", signed=True) ^ 0x424F4F4B  # "BOOK"
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _event(
    db: Session, activity: Activity, kind: str, details: dict[str, object], actor: uuid.UUID | None
) -> None:
    db.add(ActivityEvent(activity_id=activity.id, kind=kind, details=details, actor_id=actor))


def _locked_activity(db: Session, activity_id: uuid.UUID) -> Activity | None:
    return db.scalar(
        select(Activity).where(Activity.id == activity_id).with_for_update(of=Activity)
    )


def _local(moment: datetime) -> str:
    return long_datetime(moment.astimezone(availability.tz()))


def tell_customer(db: Session, booking: Booking, text_: str) -> None:
    enqueue(
        db,
        booking.contact_channel,
        Purpose.NOTIFICATION,
        booking.contact_address,
        subject="رزرو جلسه" if booking.contact_channel is Channel.EMAIL else None,
        body=text_,
    )


def _tell_staff(db: Session, booking: Booking, title: str, key: str) -> None:
    notify(
        db,
        booking.user_id,
        NotificationKind.BOOKING,
        title,
        key,
        body=f"{booking.meeting_type.title} — {_local(booking.start_at)}",
        link=f"/customers/{booking.customer_id}",
    )


def _check_free(
    db: Session, link: BookingLink, start_at: datetime, replacing: Booking | None
) -> datetime:
    lock_calendar(db, link.user_id)
    calendar = availability.load(db, link.user_id, ignore_booking=replacing)
    if not link.meeting_type.is_active or not availability.is_free(
        calendar, link.meeting_type, start_at
    ):
        raise SlotTakenError
    return start_at.astimezone(UTC)


def _insert(db: Session, booking: Booking) -> None:
    try:
        with db.begin_nested():
            db.add(booking)
    except IntegrityError as exc:  # the exclusion constraint: someone else got there
        raise SlotTakenError from exc


def book(
    db: Session,
    link: BookingLink,
    start_at: datetime,
    contact: tuple[Channel, str],
    manage_url: str,
) -> Booking:
    """Creates the booking and its meeting activity. The caller commits."""
    start = _check_free(db, link, start_at, None)
    meeting = link.meeting_type
    local = start.astimezone(availability.tz())
    activity = Activity(
        type=ActivityType.MEETING,
        title=meeting.title,
        description="رزرو شده توسط مشتری از لینک زمان‌های آزاد."
        + (f"\n{meeting.description}" if meeting.description else ""),
        owner_id=link.user_id,
        created_by_id=link.created_by_id,
        due_date=local.date(),
        start_at=start,
        duration_minutes=meeting.duration_minutes,
        reminder_minutes=LINK_STAFF_REMINDER_MINUTES,
        customer_id=link.customer_id,
        deal_id=link.deal_id,
    )
    refresh_reminder(activity)
    db.add(activity)
    db.flush()
    booking = Booking(
        link_id=link.id,
        user_id=link.user_id,
        customer_id=link.customer_id,
        deal_id=link.deal_id,
        meeting_type_id=meeting.id,
        activity_id=activity.id,
        start_at=start,
        end_at=start + timedelta(minutes=meeting.duration_minutes),
        status=BookingStatus.CONFIRMED,
        contact_channel=contact[0],
        contact_address=contact[1],
    )
    _insert(db, booking)
    db.flush()
    db.refresh(booking)
    _event(db, activity, "created", {**schedule_snapshot(activity), "by": "customer"}, None)
    _tell_staff(db, booking, f"رزرو جلسه: {link.customer.full_name}", f"booking:{booking.id}")
    tell_customer(
        db,
        booking,
        f"رزرو شما ثبت شد: «{meeting.title}» با {link.user.full_name}، {_local(start)}."
        f"\nلغو یا تغییر زمان: {manage_url}",
    )
    return booking


def reschedule(db: Session, booking: Booking, start_at: datetime, manage_url: str) -> Booking:
    """Books the new time and frees the old one in one transaction. The caller commits."""
    link = booking.link
    start = _check_free(db, link, start_at, booking)
    activity = _locked_activity(db, booking.activity_id)
    if activity is None or activity.status not in OPEN_STATUSES:
        raise SlotTakenError
    replacement = Booking(
        link_id=link.id,
        user_id=booking.user_id,
        customer_id=booking.customer_id,
        deal_id=booking.deal_id,
        meeting_type_id=booking.meeting_type_id,
        activity_id=booking.activity_id,
        start_at=start,
        end_at=start + (booking.end_at - booking.start_at),
        status=BookingStatus.CONFIRMED,
        contact_channel=booking.contact_channel,
        contact_address=booking.contact_address,
    )
    booking.status = BookingStatus.RESCHEDULED
    db.flush()  # free the old time before taking the new one
    _insert(db, replacement)
    db.flush()
    booking.rescheduled_to_id = replacement.id
    before = schedule_snapshot(activity)
    activity.start_at = start
    activity.due_date = start.astimezone(availability.tz()).date()
    refresh_reminder(activity)
    activity.version += 1
    _event(
        db,
        activity,
        "rescheduled",
        {"from": before, "to": schedule_snapshot(activity), "by": "customer"},
        None,
    )
    db.flush()
    db.refresh(replacement)
    _tell_staff(
        db,
        replacement,
        f"تغییر زمان جلسه: {booking.customer.full_name}",
        f"booking:{replacement.id}",
    )
    tell_customer(
        db,
        replacement,
        f"زمان «{replacement.meeting_type.title}» به {_local(start)} تغییر کرد."
        f"\nلغو یا تغییر دوباره: {manage_url}",
    )
    return replacement


def cancel(
    db: Session,
    booking: Booking,
    reason: str | None,
    *,
    by_user: uuid.UUID | None = None,
    cancel_activity: bool = True,
) -> None:
    """Cancels the booking (and, unless the activity is being canceled already, its
    meeting activity) and tells the other side. The caller commits."""
    now = datetime.now(UTC)
    booking.status = BookingStatus.CANCELED
    booking.canceled_at = now
    booking.canceled_by_id = by_user
    booking.cancel_reason = (reason or "").strip()[:300] or None
    who = "مشتری" if by_user is None else "کارشناس"
    if cancel_activity:
        activity = _locked_activity(db, booking.activity_id)
        if activity is not None and activity.status in OPEN_STATUSES:
            activity.status = ActivityStatus.CANCELED
            activity.cancel_reason = f"لغو رزرو توسط {who}" + (
                f": {booking.cancel_reason}" if booking.cancel_reason else ""
            )
            activity.version += 1
            _event(
                db,
                activity,
                "canceled",
                {
                    "reason": activity.cancel_reason,
                    "by": "customer" if by_user is None else "staff",
                },
                by_user,
            )
    meeting = booking.meeting_type.title
    if by_user is None:
        _tell_staff(
            db,
            booking,
            f"لغو جلسه توسط مشتری: {booking.customer.full_name}",
            f"cancel:{booking.id}",
        )
        tell_customer(db, booking, f"«{meeting}» در {_local(booking.start_at)} لغو شد.")
    else:
        tell_customer(
            db,
            booking,
            f"«{meeting}» در {_local(booking.start_at)} از طرف ما لغو شد. "
            "برای هماهنگی زمان دیگر با شما تماس می‌گیریم.",
        )


def booking_of_activity(db: Session, activity_id: uuid.UUID) -> Booking | None:
    return db.scalar(
        select(Booking).where(
            Booking.activity_id == activity_id, Booking.status == BookingStatus.CONFIRMED
        )
    )


def send_customer_reminders(db: Session, now: datetime) -> int:
    """A day before (scheduler job): one reminder per booking, if it was booked early
    enough for a reminder to make sense."""
    due = db.scalars(
        select(Booking)
        .where(
            Booking.status == BookingStatus.CONFIRMED,
            Booking.customer_reminded_at.is_(None),
            Booking.start_at > now,
            Booking.start_at <= now + timedelta(hours=CUSTOMER_REMINDER_HOURS),
        )
        .limit(200)
        .with_for_update(skip_locked=True, of=Booking)
    ).unique()
    sent = 0
    for booking in due:
        booking.customer_reminded_at = now
        if booking.start_at - booking.created_at < CUSTOMER_REMINDER_MIN_LEAD:
            continue
        tell_customer(
            db,
            booking,
            f"یادآوری: «{booking.meeting_type.title}» با {booking.user.full_name}، "
            f"{_local(booking.start_at)}.",
        )
        sent += 1
    return sent


def raise_taken() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail="این زمان همین حالا رزرو شد یا دیگر آزاد نیست. یکی از زمان‌های آزاد را انتخاب کنید.",
    )
