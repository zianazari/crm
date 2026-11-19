"""Customer portal identities and sessions (spec 4.9, section 5, 9: PortalIdentity).

* A portal identity ties one verified address (a mobile or an email) to one customer.
  Staff turn it on from the customer's record using the address on file; similar
  names, companies or email domains never give access.
* An address can open the portal for one customer only (unique per channel), so a
  login is never ambiguous.
* Sessions are opaque random tokens; only their hash is stored. Turning access off
  revokes every session of that identity at once.
* Portal identities are not staff users and share no table, cookie or permission
  with them.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKey
from app.modules.crm.models import Customer
from app.modules.messaging.models import Channel


class PortalIdentity(UUIDPrimaryKey, Base):
    __tablename__ = "portal_identities"
    __table_args__ = (UniqueConstraint("channel", "address"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[Channel] = mapped_column(
        Enum(Channel, name="message_channel", values_callable=lambda e: [m.value for m in e])
    )
    address: Mapped[str] = mapped_column(String(254))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(lazy="joined")


class PortalSession(UUIDPrimaryKey, Base):
    __tablename__ = "portal_sessions"

    identity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_identities.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(64))

    identity: Mapped[PortalIdentity] = relationship(lazy="joined")
