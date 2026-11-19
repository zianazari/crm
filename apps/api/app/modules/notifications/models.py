"""In-app notifications (spec 4.2 "in-app reminder"; 5 owner changes).

A notification only ever goes to someone who may open what it links to: the
activity's assignee, or the new owner of a record. ``dedupe_key`` makes every
producer safe to run twice (a scheduler restart, a repeated event).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class NotificationKind(enum.StrEnum):
    ACTIVITY_REMINDER = "activity_reminder"
    ACTIVITY_ASSIGNED = "activity_assigned"
    RECORD_ASSIGNED = "record_assigned"
    DAILY_DIGEST = "daily_digest"
    TEAM_TASK = "team_task"  # new work in a team queue
    CAMPAIGN = "campaign"  # a campaign finished, failed or hit the budget
    TICKET = "ticket"  # a ticket was opened, answered by the customer, or assigned


class Notification(UUIDPrimaryKey, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(
            NotificationKind,
            name="notification_kind",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(200))
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
