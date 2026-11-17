"""Customers, organizations and leads (spec sections 3, 4.1, 9 and section 0 decisions 3–4).

* A customer is always a person. A person may buy personally or represent one or
  more organizations (``customer_organizations``).
* Every lead and customer has exactly one owner; changes are kept in
  ``ownership_history``.
* Records are archived (soft-deleted) with actor and time, never hard-deleted here.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.identity.models import User


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class LeadStatus(enum.StrEnum):
    NEW = "new"
    WORKING = "working"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    CONVERTED = "converted"


class ContactChannel(enum.StrEnum):
    PHONE = "phone"
    SMS = "sms"
    EMAIL = "email"


class LeadSource(UUIDPrimaryKey, Timestamps, Base):
    """Admin-defined acquisition sources (site, referral, social, ads, inbound call, manual)."""

    __tablename__ = "lead_sources"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)


class Tag(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(50), unique=True)


lead_tags = Table(
    "lead_tags",
    Base.metadata,
    Column("lead_id", ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

customer_tags = Table(
    "customer_tags",
    Base.metadata,
    Column("customer_id", ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Archivable:
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Organization(UUIDPrimaryKey, Timestamps, Archivable, Base):
    """A company or institution. Shared reference data: visible to all staff."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    website: Mapped[str | None] = mapped_column(String(200))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    members: Mapped[list["CustomerOrganization"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class Customer(UUIDPrimaryKey, Timestamps, Archivable, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "mobile IS NOT NULL OR email IS NOT NULL OR phone IS NOT NULL", name="has_contact"
        ),
    )

    full_name: Mapped[str] = mapped_column(String(160), index=True)
    # Normalized (E.164 / lower-case). Not unique: family members or colleagues may
    # share a number; duplicates are detected and the user decides (spec section 4.1).
    mobile: Mapped[str | None] = mapped_column(String(20), index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    preferred_channel: Mapped[ContactChannel | None] = mapped_column(
        _enum(ContactChannel, "contact_channel")
    )
    description: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lead_sources.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(foreign_keys=[owner_id], lazy="joined")
    source: Mapped[LeadSource | None] = relationship(lazy="joined")
    tags: Mapped[list[Tag]] = relationship(secondary=customer_tags, lazy="selectin")
    organizations: Mapped[list["CustomerOrganization"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", lazy="selectin"
    )


class CustomerOrganization(Timestamps, Base):
    """A person representing an organization, with their role there."""

    __tablename__ = "customer_organizations"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    job_title: Mapped[str | None] = mapped_column(String(120))

    customer: Mapped[Customer] = relationship(back_populates="organizations")
    organization: Mapped[Organization] = relationship(back_populates="members", lazy="joined")


class Lead(UUIDPrimaryKey, Timestamps, Archivable, Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint("mobile IS NOT NULL OR email IS NOT NULL", name="has_contact"),
        CheckConstraint(
            "status <> 'disqualified' OR disqualify_reason IS NOT NULL",
            name="disqualified_has_reason",
        ),
        CheckConstraint(
            "(status = 'converted') = (converted_customer_id IS NOT NULL)",
            name="converted_has_customer",
        ),
    )

    full_name: Mapped[str] = mapped_column(String(160), index=True)
    mobile: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(254), index=True)
    company_name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lead_sources.id"), index=True)
    # Campaign / UTM details when available (spec section 4.1).
    acquisition: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[LeadStatus] = mapped_column(
        _enum(LeadStatus, "lead_status"), default=LeadStatus.NEW, index=True
    )
    disqualify_reason: Mapped[str | None] = mapped_column(String(300))
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id"), index=True
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    owner: Mapped[User] = relationship(foreign_keys=[owner_id], lazy="joined")
    source: Mapped[LeadSource | None] = relationship(lazy="joined")
    tags: Mapped[list[Tag]] = relationship(secondary=lead_tags, lazy="selectin")


class OwnershipHistory(UUIDPrimaryKey, Base):
    """Every owner change of a lead or customer (spec section 4.1)."""

    __tablename__ = "ownership_history"

    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    from_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    changed_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(300))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
