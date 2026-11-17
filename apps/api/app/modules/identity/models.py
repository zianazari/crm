"""Staff identity: users, roles and teams (spec sections 5 and 9).

Customer portal identities are a separate model (PortalIdentity, release 2);
they never share this table.
"""

import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Role(enum.StrEnum):
    ADMIN = "admin"
    SALES_MANAGER = "sales_manager"
    SALES_REP = "sales_rep"


class Team(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    # A manager runs exactly one team (spec section 0, decision 4), hence unique.
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, ondelete="SET NULL"), unique=True
    )

    manager: Mapped["User | None"] = relationship(foreign_keys=[manager_id])
    members: Mapped[list["User"]] = relationship(back_populates="team", foreign_keys="User.team_id")


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("mobile IS NOT NULL OR email IS NOT NULL", name="has_login_destination"),
    )

    full_name: Mapped[str] = mapped_column(String(160))
    # Stored normalized (mobile as E.164, email lower-cased) so lookups and uniqueness are exact.
    mobile: Mapped[str | None] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda e: [m.value for m in e])
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True)

    team: Mapped[Team | None] = relationship(back_populates="members", foreign_keys=[team_id])
