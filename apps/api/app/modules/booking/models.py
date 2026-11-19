"""Staff availability and customer bookings (spec 4.10; section 9: AvailabilityRule,
AvailabilityException, BookingLink, Booking).

* Each staff member has booking settings (buffers, notice, horizon, change deadline),
  weekly working hours and meeting types. Days off are exceptions: a person's leave, or
  an organization holiday when ``user_id`` is empty.
* A booking link is a random token (only its hash is stored) for one customer and one
  meeting type in one person's calendar. It expires and can be revoked; holding it only
  shows free times, never the customer's record.
* A confirmed booking always has a meeting activity. Rescheduling marks the old booking
  ``rescheduled`` and points it at the new one, so the history stays; the activity moves.
* Free time is checked and the booking written under a per-calendar advisory lock, and
  an exclusion constraint (migration ``booking``) makes two confirmed bookings of one
  person overlapping impossible even if that check were bypassed.
"""

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.crm.models import Customer
from app.modules.identity.models import User
from app.modules.messaging.models import Channel


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class BookingSettings(Base):
    __tablename__ = "booking_settings"
    __table_args__ = (
        CheckConstraint(
            "buffer_before_minutes BETWEEN 0 AND 240 AND buffer_after_minutes BETWEEN 0 AND 240",
            name="buffers_in_range",
        ),
        CheckConstraint("min_notice_minutes BETWEEN 0 AND 20160", name="notice_in_range"),
        CheckConstraint("horizon_days BETWEEN 1 AND 180", name="horizon_in_range"),
        CheckConstraint("change_deadline_hours BETWEEN 0 AND 336", name="deadline_in_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    buffer_before_minutes: Mapped[int] = mapped_column(default=0)
    buffer_after_minutes: Mapped[int] = mapped_column(default=10)
    # A customer cannot book sooner than this from now.
    min_notice_minutes: Mapped[int] = mapped_column(default=240)
    # How many days ahead a customer can book.
    horizon_days: Mapped[int] = mapped_column(default=30)
    # A customer can cancel or move a booking until this many hours before it.
    change_deadline_hours: Mapped[int] = mapped_column(default=24)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AvailabilityRule(UUIDPrimaryKey, Base):
    """Weekly working hours. ``weekday`` 0 is Saturday, the first day of the week."""

    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_in_range"),
        CheckConstraint("start_time < end_time", name="starts_before_end"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class AvailabilityException(UUIDPrimaryKey, Base):
    """Whole days off: leave for one person, or a holiday for everyone (no user)."""

    __tablename__ = "availability_exceptions"
    __table_args__ = (CheckConstraint("start_date <= end_date", name="starts_before_end"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(200))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MeetingType(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "meeting_types"
    __table_args__ = (
        CheckConstraint("duration_minutes BETWEEN 10 AND 480", name="duration_in_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    duration_minutes: Mapped[int]
    # Shown to the customer: where or how the meeting happens.
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(default=True)

    user: Mapped[User] = relationship(lazy="joined")


class BookingLink(UUIDPrimaryKey, Base):
    __tablename__ = "booking_links"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Whose calendar the customer books into.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL"))
    meeting_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meeting_types.id"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # How it was sent to the customer, if it was (otherwise only copied).
    sent_via: Mapped[Channel | None] = mapped_column(
        Enum(Channel, name="message_channel", values_callable=lambda e: [m.value for m in e])
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id], lazy="joined")
    customer: Mapped[Customer] = relationship(lazy="joined")
    meeting_type: Mapped[MeetingType] = relationship(lazy="joined")


class BookingStatus(enum.StrEnum):
    CONFIRMED = "confirmed"
    CANCELED = "canceled"
    RESCHEDULED = "rescheduled"  # replaced by ``rescheduled_to``


class Booking(UUIDPrimaryKey, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="starts_before_end"),
        CheckConstraint(
            "status <> 'canceled' OR canceled_at IS NOT NULL", name="canceled_has_time"
        ),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("booking_links.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL"))
    meeting_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meeting_types.id"))
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(
        _enum(BookingStatus, "booking_status"), default=BookingStatus.CONFIRMED, index=True
    )
    # The verified address confirmations and reminders go to.
    contact_channel: Mapped[Channel] = mapped_column(
        Enum(Channel, name="message_channel", values_callable=lambda e: [m.value for m in e])
    )
    contact_address: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Empty when the customer canceled; the staff member otherwise.
    canceled_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    rescheduled_to_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id"))
    customer_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    link: Mapped[BookingLink] = relationship(lazy="joined")
    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")
    customer: Mapped[Customer] = relationship(lazy="joined")
    meeting_type: Mapped[MeetingType] = relationship(lazy="joined")
    canceled_by: Mapped[User | None] = relationship(foreign_keys=[canceled_by_id], lazy="joined")
