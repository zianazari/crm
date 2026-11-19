"""Support tickets (spec 4.9, 9: Ticket, TicketMessage).

* A ticket belongs to one customer; it is opened from the portal by that customer, or
  by staff on the customer's behalf. Its tracking number is a plain sequence.
* Messages are public (the customer sees them) or internal (staff only). The portal
  never reads internal messages.
* Statuses: new, in progress, waiting for the customer, closed.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.crm.models import Customer
from app.modules.identity.models import User


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class TicketStatus(enum.StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    CLOSED = "closed"


class Ticket(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tickets"

    number: Mapped[int] = mapped_column(Identity(start=1001), unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    status: Mapped[TicketStatus] = mapped_column(
        _enum(TicketStatus, "ticket_status"), default=TicketStatus.NEW, index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    # Who opened it: the customer (portal identity) or a staff member.
    opened_by_identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portal_identities.id", ondelete="SET NULL")
    )
    opened_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1)

    customer: Mapped[Customer] = relationship(lazy="joined")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="joined")
    opened_by_user: Mapped[User | None] = relationship(
        foreign_keys=[opened_by_user_id], lazy="joined"
    )


class TicketMessage(UUIDPrimaryKey, Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        CheckConstraint(
            "(author_user_id IS NULL) <> (author_identity_id IS NULL)", name="one_author"
        ),
        CheckConstraint("NOT internal OR author_user_id IS NOT NULL", name="internal_by_staff"),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    # Internal notes are for staff only and never leave the staff API.
    internal: Mapped[bool] = mapped_column(default=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Portal identities are only ever disabled, never deleted.
    author_identity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("portal_identities.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author_user: Mapped[User | None] = relationship(lazy="joined")
