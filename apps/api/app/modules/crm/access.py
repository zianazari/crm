"""Record-level access rules for owned records (spec section 5 and section 0, decision 4).

* admin: full access to everything; can assign to anyone; can archive and restore.
* sales_manager: full access to records owned by themselves or members of the
  one team they manage; can assign within that team; can archive and restore there.
* sales_rep: full access to records they own; can create records only for themselves.

Everyone else's records are visible in "limited" form only: name, status, owner and
last activity — no contact details, notes or history, and no edits.

These checks are enforced in the API for every read, list, search and write; the UI
only mirrors them.
"""

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, false, select, true
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.identity.models import Role, Team, User

FORBIDDEN = HTTPException(
    status.HTTP_403_FORBIDDEN,
    detail="دسترسی به این پرونده را ندارید. برای پیگیری با مسئول پرونده یا مدیر تماس بگیرید.",
)


@dataclass(frozen=True)
class AccessScope:
    user: User
    # For a manager: ids of active members of their team (including themselves).
    team_member_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    @property
    def is_admin(self) -> bool:
        return self.user.role is Role.ADMIN

    @property
    def is_manager(self) -> bool:
        return self.user.role is Role.SALES_MANAGER

    def has_full_access(self, owner_id: uuid.UUID) -> bool:
        if self.is_admin or owner_id == self.user.id:
            return True
        return self.is_manager and owner_id in self.team_member_ids

    def can_manage(self, owner_id: uuid.UUID) -> bool:
        """Assign, archive and restore: admins, and managers within their team."""
        return self.is_admin or (self.is_manager and owner_id in self.team_member_ids)

    def can_assign_to(self, user: User) -> bool:
        if not user.is_active:
            return False
        if self.is_admin:
            return True
        if self.is_manager:
            return user.id in self.team_member_ids
        return user.id == self.user.id

    def owner_ids(self) -> set[uuid.UUID] | None:
        """Owners whose records this user sees in full; None means everyone (admin)."""
        if self.is_admin:
            return None
        return {self.user.id} | (set(self.team_member_ids) if self.is_manager else set())

    def full_access_filter(
        self, owner_column: InstrumentedAttribute[uuid.UUID]
    ) -> ColumnElement[bool]:
        """SQL condition for rows this user may see in full."""
        if self.is_admin:
            return true()
        ids = {self.user.id} | (set(self.team_member_ids) if self.is_manager else set())
        return owner_column.in_(ids) if ids else false()

    def require_full(self, owner_id: uuid.UUID) -> None:
        if not self.has_full_access(owner_id):
            raise FORBIDDEN

    def require_manage(self, owner_id: uuid.UUID) -> None:
        if not self.can_manage(owner_id):
            raise FORBIDDEN


def build_scope(db: Session, user: User) -> AccessScope:
    if user.role is not Role.SALES_MANAGER:
        return AccessScope(user=user)
    team_id = db.scalar(select(Team.id).where(Team.manager_id == user.id, Team.is_active.is_(True)))
    members: set[uuid.UUID] = {user.id}
    if team_id is not None:
        members |= set(
            db.scalars(select(User.id).where(User.team_id == team_id, User.is_active.is_(True)))
        )
    return AccessScope(user=user, team_member_ids=frozenset(members))
