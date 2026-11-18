"""Activities, their change log, and notes (spec sections 4.2, 9).

* An activity has a calendar date and, optionally, a start time and duration. Only
  timed activities occupy time in the calendar; date-only ones never block it.
* ``version`` guards concurrent changes, so completing twice cannot happen.
* Every reschedule, reassignment, completion, cancellation and postponement is kept in
  ``activity_events``.
* Notes are internal records attached to a lead, customer or deal; they are not
  messages sent to anyone.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.crm.models import Customer, Lead
from app.modules.identity.models import User
from app.modules.sales.models import Deal


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class ActivityType(enum.StrEnum):
    CALL = "call"
    MEETING = "meeting"
    FOLLOW_UP = "follow_up"
    TASK = "task"


class ActivityStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELED = "canceled"


OPEN_STATUSES = (ActivityStatus.PENDING, ActivityStatus.IN_PROGRESS)


class Priority(enum.StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Activity(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint(
            "duration_minutes IS NULL OR (duration_minutes > 0 AND start_at IS NOT NULL)",
            name="duration_needs_start",
        ),
        CheckConstraint("status <> 'done' OR completed_at IS NOT NULL", name="done_has_time"),
        CheckConstraint(
            "status <> 'canceled' OR cancel_reason IS NOT NULL", name="canceled_has_reason"
        ),
        CheckConstraint(
            "reminder_minutes IS NULL OR reminder_minutes >= 0", name="reminder_not_negative"
        ),
    )

    type: Mapped[ActivityType] = mapped_column(_enum(ActivityType, "activity_type"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Calendar date in the organization's time zone; for timed activities it is the
    # local date of start_at.
    due_date: Mapped[date] = mapped_column(Date, index=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    duration_minutes: Mapped[int | None]
    priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "activity_priority"), default=Priority.NORMAL
    )
    reminder_minutes: Mapped[int | None]
    # When the in-app reminder is due, and when it was sent (reset on reschedule).
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ActivityStatus] = mapped_column(
        _enum(ActivityStatus, "activity_status"), default=ActivityStatus.PENDING, index=True
    )
    outcome: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    version: Mapped[int] = mapped_column(default=1)

    owner: Mapped[User] = relationship(foreign_keys=[owner_id], lazy="joined")
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id], lazy="joined")
    completed_by: Mapped[User | None] = relationship(foreign_keys=[completed_by_id], lazy="joined")
    lead: Mapped[Lead | None] = relationship(lazy="selectin")
    customer: Mapped[Customer | None] = relationship(lazy="selectin")
    deal: Mapped[Deal | None] = relationship(lazy="selectin")


class ActivityEvent(UUIDPrimaryKey, Base):
    __tablename__ = "activity_events"

    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped[User] = relationship(lazy="joined")


class Note(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "lead_id IS NOT NULL OR customer_id IS NOT NULL OR deal_id IS NOT NULL",
            name="has_subject",
        ),
    )

    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)

    author: Mapped[User] = relationship(lazy="joined")
