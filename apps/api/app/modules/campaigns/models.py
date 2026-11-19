"""SMS and email campaigns (spec 4.5, 9: Campaign, CampaignRecipient, Suppression).

* A campaign targets chosen contacts or a filtered segment. Its recipient list is fixed
  when it starts running; until then only previews are computed.
* Each recipient is checked again right before their message is queued: consent, the
  do-not-send list, a usable address, the sending window and the daily and monthly
  limits. Duplicates (the same address twice) get one message; the rest are recorded as
  skipped with the reason.
* Pausing stops what has not started: recipients not yet queued wait, and queued
  messages are canceled (and re-queued on resume). A sent message cannot be recalled.
* The do-not-send list (``Suppression``) applies to marketing only; logins and
  operational messages have their own path.
"""

import enum
import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.identity.models import User
from app.modules.messaging.models import Channel, OutboundMessage


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class CampaignStatus(enum.StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"  # finished without a single message accepted


class Campaign(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(120))
    channel: Mapped[Channel] = mapped_column(_enum(Channel, "message_channel"))
    subject: Mapped[str | None] = mapped_column(String(200))  # email only
    body: Mapped[str] = mapped_column(Text, default="")
    # {"kind": "selected", "contacts": [{"type": "lead"|"customer", "id": ...}]}
    # {"kind": "segment", "filters": {...}}  (see audience.py)
    audience: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[CampaignStatus] = mapped_column(
        _enum(CampaignStatus, "campaign_status"), default=CampaignStatus.DRAFT, index=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why a running campaign is not sending right now (window, daily limit), or why it
    # was paused automatically (monthly budget).
    waiting_reason: Mapped[str | None] = mapped_column(String(300))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(default=1)

    created_by: Mapped[User] = relationship(lazy="joined")


class RecipientStatus(enum.StrEnum):
    PENDING = "pending"  # on the list, not yet queued
    QUEUED = "queued"  # a message exists; its own status tells the rest
    SKIPPED = "skipped"  # not sent; ``skip_reason`` says why


class CampaignRecipient(UUIDPrimaryKey, Base):
    __tablename__ = "campaign_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_type", "contact_id"),
        CheckConstraint(
            "status <> 'skipped' OR skip_reason IS NOT NULL", name="skipped_has_reason"
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    contact_type: Mapped[str] = mapped_column(String(10))  # lead | customer
    contact_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(String(254))  # normalized at snapshot
    status: Mapped[RecipientStatus] = mapped_column(
        _enum(RecipientStatus, "campaign_recipient_status"),
        default=RecipientStatus.PENDING,
        index=True,
    )
    skip_reason: Mapped[str | None] = mapped_column(String(200))
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbound_messages.id", ondelete="SET NULL"), unique=True
    )
    cost: Mapped[int] = mapped_column(BigInteger, default=0)  # toman, estimated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    message: Mapped[OutboundMessage | None] = relationship(lazy="joined")


class Suppression(UUIDPrimaryKey, Base):
    """The do-not-send list for marketing, per channel and address."""

    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("channel", "address"),)

    channel: Mapped[Channel] = mapped_column(_enum(Channel, "message_channel"))
    address: Mapped[str] = mapped_column(String(254))
    reason: Mapped[str] = mapped_column(String(20))  # unsubscribed | manual
    note: Mapped[str | None] = mapped_column(String(300))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessagingPolicy(Base):
    """Admin-set sending rules for marketing (spec 4.5); a single row (id = 1)."""

    __tablename__ = "messaging_policy"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("window_start < window_end", name="window_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    # Local (Asia/Tehran) hours in which marketing may be sent.
    window_start: Mapped[time] = mapped_column(Time, default=time(9, 0))
    window_end: Mapped[time] = mapped_column(Time, default=time(21, 0))
    sms_daily_limit: Mapped[int] = mapped_column(default=1000)
    email_daily_limit: Mapped[int] = mapped_column(default=5000)
    # Estimated price per SMS part and per email, in toman (until a provider is chosen).
    sms_unit_price: Mapped[int] = mapped_column(BigInteger, default=0)
    email_unit_price: Mapped[int] = mapped_column(BigInteger, default=0)
    # Marketing spend allowed in any rolling 30 days (toman); None = no limit.
    monthly_budget: Mapped[int | None] = mapped_column(BigInteger)
    # One-off template messages a person may send per day from their own records.
    user_daily_limit: Mapped[int] = mapped_column(default=20, server_default="20")
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TemplateKind(enum.StrEnum):
    SERVICE = "service"  # information about the customer's own business, e.g. an invoice
    MARKETING = "marketing"  # promotional: consent, do-not-send list, window, unsubscribe


class MessageTemplate(UUIDPrimaryKey, Timestamps, Base):
    """An approved text that staff may send one at a time (spec section 5); written by
    managers and admins, so reps never send free text from the system."""

    __tablename__ = "message_templates"

    name: Mapped[str] = mapped_column(String(120))
    channel: Mapped[Channel] = mapped_column(_enum(Channel, "message_channel"))
    kind: Mapped[TemplateKind] = mapped_column(_enum(TemplateKind, "message_template_kind"))
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class DirectMessage(UUIDPrimaryKey, Base):
    """One template sent by a person from a record; shown on that record's timeline."""

    __tablename__ = "direct_messages"
    __table_args__ = (
        # A retried request (double click, flaky network) never sends twice.
        UniqueConstraint("sender_id", "request_id"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("message_templates.id"))
    template_name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[TemplateKind] = mapped_column(_enum(TemplateKind, "message_template_kind"))
    channel: Mapped[Channel] = mapped_column(_enum(Channel, "message_channel"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[uuid.UUID]
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    contact_name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(254))
    text: Mapped[str] = mapped_column(Text)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbound_messages.id", ondelete="SET NULL"), unique=True
    )
    cost: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    sender: Mapped[User] = relationship(lazy="joined")
    message: Mapped[OutboundMessage | None] = relationship(lazy="joined")
