"""Outbound messages, their delivery events, and the transactional outbox (spec 7, 9).

Statuses of a message:
  queued -> sending -> accepted -> delivered | failed
  queued -> expired        (an OTP whose challenge ended before sending)
  sending -> unknown       (the provider may have the message but never answered;
                            never re-sent blindly — needs reconciliation)
  queued -> failed         (permanent error, or attempts exhausted)
  queued -> canceled       (marketing: the campaign was paused, or the address was
                            put on the do-not-send list, before sending started)
"accepted" means the provider took the message, not that it was delivered.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Channel(enum.StrEnum):
    SMS = "sms"
    EMAIL = "email"


class Purpose(enum.StrEnum):
    OTP = "otp"
    NOTIFICATION = "notification"
    MARKETING = "marketing"  # campaigns: subject to consent and the do-not-send list


class MessageStatus(enum.StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    CANCELED = "canceled"


FINAL_STATUSES = {
    MessageStatus.CANCELED,
    MessageStatus.ACCEPTED,
    MessageStatus.DELIVERED,
    MessageStatus.FAILED,
    MessageStatus.UNKNOWN,
    MessageStatus.EXPIRED,
}


class OutboundMessage(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "outbound_messages"

    channel: Mapped[Channel] = mapped_column(_enum(Channel, "message_channel"))
    purpose: Mapped[Purpose] = mapped_column(_enum(Purpose, "message_purpose"), index=True)
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str | None] = mapped_column(String(200))
    # Null for OTP: the code lives only in Redis for the challenge's lifetime.
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MessageStatus] = mapped_column(
        _enum(MessageStatus, "message_status"), default=MessageStatus.QUEUED, index=True
    )
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    provider_message_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    # OTP: the challenge this code belongs to; a newer challenge makes it obsolete.
    challenge_id: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliveryEvent(UUIDPrimaryKey, Base):
    """Provider delivery reports; ``provider_event_id`` makes repeats harmless."""

    __tablename__ = "delivery_events"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outbound_messages.id", ondelete="CASCADE"), index=True
    )
    provider_event_id: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(30))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEvent(UUIDPrimaryKey, Base):
    """Written in the same transaction as the change it announces; a publisher moves it
    to RabbitMQ, so a committed message is never lost if the broker is down."""

    __tablename__ = "outbox_events"

    routing_key: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    publish_attempts: Mapped[int] = mapped_column(default=0)
