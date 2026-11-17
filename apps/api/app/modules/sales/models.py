"""Deals, pipeline stages and payments (spec sections 3, 4.3, 9 and section 0 decisions 1–2).

* A deal is open in one of the active stages, or closed as won / lost. Won and lost
  are statuses, not stages; the board shows them together in a "final result" column.
* Won means a signed contract: contract amount and date are required.
* Amounts are whole toman stored as BIGINT (exact, no floating point).
* Payments and refunds are never deleted; a mistaken entry is voided with a reason.
* ``version`` increases on every change so concurrent board moves are detected.
"""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.crm.models import Archivable, Customer, Organization
from app.modules.identity.models import User


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class DealStatus(enum.StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"


class PaymentKind(enum.StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"


class Stage(UUIDPrimaryKey, Timestamps, Base):
    """A step of the sales pipeline. Names and order are set by managers."""

    __tablename__ = "pipeline_stages"

    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class Deal(UUIDPrimaryKey, Timestamps, Archivable, Base):
    __tablename__ = "deals"
    __table_args__ = (
        CheckConstraint("amount IS NULL OR amount >= 0", name="amount_not_negative"),
        CheckConstraint(
            "status <> 'won' OR (contract_amount IS NOT NULL AND contract_date IS NOT NULL)",
            name="won_has_contract",
        ),
        CheckConstraint(
            "contract_amount IS NULL OR contract_amount >= 0", name="contract_not_negative"
        ),
        CheckConstraint("status <> 'lost' OR lost_reason IS NOT NULL", name="lost_has_reason"),
        CheckConstraint("(status = 'open') = (closed_at IS NULL)", name="closed_at_matches_status"),
    )

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # Reporting attribution (spec 4.4): owner when the deal was created and when it closed.
    created_owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    closed_owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"), index=True)
    status: Mapped[DealStatus] = mapped_column(
        _enum(DealStatus, "deal_status"), default=DealStatus.OPEN, index=True
    )
    amount: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="IRT")
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    contract_amount: Mapped[int | None] = mapped_column(BigInteger)
    contract_date: Mapped[date | None] = mapped_column(Date)
    lost_reason: Mapped[str | None] = mapped_column(String(300))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1)

    customer: Mapped[Customer] = relationship(lazy="joined")
    organization: Mapped[Organization | None] = relationship(lazy="joined")
    owner: Mapped[User] = relationship(foreign_keys=[owner_id], lazy="joined")
    stage: Mapped[Stage] = relationship(lazy="joined")


class DealHistory(UUIDPrimaryKey, Base):
    """Every stage / status change of a deal, with who did it and the owner at that time."""

    __tablename__ = "deal_history"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pipeline_stages.id"))
    to_stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"))
    from_status: Mapped[DealStatus | None] = mapped_column(_enum(DealStatus, "deal_status"))
    to_status: Mapped[DealStatus] = mapped_column(_enum(DealStatus, "deal_status"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    changed_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(300))
    # E.g. the contract details that were cleared when a won deal was reopened.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    from_stage: Mapped[Stage | None] = relationship(foreign_keys=[from_stage_id], lazy="joined")
    to_stage: Mapped[Stage] = relationship(foreign_keys=[to_stage_id], lazy="joined")
    changed_by: Mapped[User] = relationship(foreign_keys=[changed_by_id], lazy="joined")


class Payment(UUIDPrimaryKey, Timestamps, Base):
    """Money received for (or refunded on) a deal. Operational record, not accounting."""

    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"), index=True)
    kind: Mapped[PaymentKind] = mapped_column(_enum(PaymentKind, "payment_kind"))
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="IRT")
    paid_on: Mapped[date] = mapped_column(Date, index=True)
    reference: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(String(500))
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    void_reason: Mapped[str | None] = mapped_column(String(300))

    recorded_by: Mapped[User] = relationship(foreign_keys=[recorded_by_id], lazy="joined")
