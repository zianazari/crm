"""User and team administration (spec section 5).

* Only admins create, edit, deactivate and reactivate users and manage teams.
  Managers can list their own team; reps cannot list users.
* A manager runs exactly one team (section 0, decision 4).
* Deactivating a user ends every session at once and can hand their open leads,
  customers, deals and activities to someone else, with ownership history.
* Every change is written to the audit log.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, update

from app.core.normalize import normalize_email, normalize_mobile
from app.modules.activities.models import OPEN_STATUSES, Activity, ActivityEvent
from app.modules.audit.service import audit
from app.modules.auth.deps import (
    DbDep,
    RedisDep,
    SettingsDep,
    client_ip,
    require_csrf,
)
from app.modules.auth.sessions import SessionService
from app.modules.automation.events import emit
from app.modules.crm.access import AccessScope
from app.modules.crm.common import ScopeDep, unprocessable
from app.modules.crm.models import Customer, Lead, LeadStatus, OwnershipHistory
from app.modules.crm.schemas import UserRef
from app.modules.identity.models import Role, Team, User
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import fa, notify
from app.modules.sales.models import Deal, DealStatus

router = APIRouter(tags=["administration"], dependencies=[Depends(require_csrf)])

_ADMIN_ONLY = HTTPException(status.HTTP_403_FORBIDDEN, detail="این کار فقط برای ادمین مجاز است.")


def require_admin(scope: AccessScope) -> None:
    if not scope.is_admin:
        raise _ADMIN_ONLY


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    mobile: str | None
    email: str | None
    role: Role
    is_active: bool
    team: TeamRef | None
    manages_team: TeamRef | None = None


class UserIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    mobile: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=254)
    role: Role = Role.SALES_REP
    team_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    mobile: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=254)
    role: Role | None = None
    team_id: uuid.UUID | None = None


class OpenItems(BaseModel):
    leads: int
    customers: int
    deals: int
    activities: int

    @property
    def total(self) -> int:
        return self.leads + self.customers + self.deals + self.activities


class DeactivateIn(BaseModel):
    # Hand open records to this user; or explicitly leave them with the inactive user.
    transfer_to_id: uuid.UUID | None = None
    leave_open_items: bool = False


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_active: bool
    manager: UserRef | None = None
    member_count: int = 0


class TeamIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    manager_id: uuid.UUID | None = None
    is_active: bool = True


# -- helpers -----------------------------------------------------------------


def _out(db: DbDep, user: User) -> UserAdminOut:
    result = UserAdminOut.model_validate(user)
    managed = db.scalar(select(Team).where(Team.manager_id == user.id))
    result.manages_team = TeamRef.model_validate(managed) if managed else None
    return result


def _contacts(
    db: DbDep, mobile: str | None, email: str | None, exclude: uuid.UUID | None = None
) -> tuple[str | None, str | None]:
    norm_mobile = normalize_mobile(mobile) if mobile else None
    norm_email = normalize_email(email) if email else None
    if mobile and norm_mobile is None:
        raise unprocessable("شماره موبایل معتبر نیست.")
    if email and norm_email is None:
        raise unprocessable("ایمیل معتبر نیست.")
    if not (norm_mobile or norm_email):
        raise unprocessable("موبایل یا ایمیل برای ورود لازم است.")
    conditions = []
    if norm_mobile:
        conditions.append(User.mobile == norm_mobile)
    if norm_email:
        conditions.append(User.email == norm_email)
    clash = db.scalar(
        select(User).where(or_(*conditions), User.id != exclude)
        if exclude
        else select(User).where(or_(*conditions))
    )
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="این موبایل یا ایمیل برای کاربر دیگری ثبت شده است."
        )
    return norm_mobile, norm_email


def _team(db: DbDep, team_id: uuid.UUID | None) -> Team | None:
    if team_id is None:
        return None
    team = db.get(Team, team_id)
    if team is None:
        raise unprocessable("تیم معتبر نیست.")
    return team


def _open_items(db: DbDep, user_id: uuid.UUID) -> OpenItems:
    def count(query: Any) -> int:
        return int(db.scalar(query) or 0)

    return OpenItems(
        leads=count(
            select(func.count(Lead.id)).where(
                Lead.owner_id == user_id,
                Lead.archived_at.is_(None),
                Lead.status.notin_([LeadStatus.CONVERTED, LeadStatus.DISQUALIFIED]),
            )
        ),
        customers=count(
            select(func.count(Customer.id)).where(
                Customer.owner_id == user_id, Customer.archived_at.is_(None)
            )
        ),
        deals=count(
            select(func.count(Deal.id)).where(
                Deal.owner_id == user_id, Deal.status == DealStatus.OPEN, Deal.archived_at.is_(None)
            )
        ),
        activities=count(
            select(func.count(Activity.id)).where(
                Activity.owner_id == user_id, Activity.status.in_(OPEN_STATUSES)
            )
        ),
    )


# -- users ---------------------------------------------------------------------


@router.get("/users")
def list_users(db: DbDep, scope: ScopeDep, include_inactive: bool = False) -> list[UserAdminOut]:
    """Admins see everyone; a manager sees their own team; reps may not list users."""
    query = select(User).order_by(User.is_active.desc(), User.full_name)
    if scope.is_manager:
        query = query.where(User.id.in_(scope.team_member_ids))
    elif not scope.is_admin:
        raise _ADMIN_ONLY
    if not include_inactive:
        query = query.where(User.is_active.is_(True))
    return [_out(db, u) for u in db.scalars(query).unique()]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserIn, request: Request, db: DbDep, scope: ScopeDep) -> UserAdminOut:
    require_admin(scope)
    mobile, email = _contacts(db, body.mobile, body.email)
    team = _team(db, body.team_id)
    user = User(
        full_name=body.full_name.strip(), mobile=mobile, email=email, role=body.role, team=team
    )
    db.add(user)
    db.flush()
    audit(
        db,
        "user.created",
        scope.user.id,
        "user",
        user.id,
        {"role": body.role.value, "team_id": str(team.id) if team else None},
        client_ip(request),
    )
    db.commit()
    return _out(db, user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: uuid.UUID, body: UserUpdate, request: Request, db: DbDep, scope: ScopeDep
) -> UserAdminOut:
    require_admin(scope)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="کاربر پیدا نشد.")
    data = body.model_dump(exclude_unset=True)
    changes: dict[str, Any] = {}

    if "mobile" in data or "email" in data:
        mobile, email = _contacts(
            db, data.get("mobile", user.mobile), data.get("email", user.email), exclude=user.id
        )
        if (mobile, email) != (user.mobile, user.email):
            changes["contact"] = "changed"
        user.mobile, user.email = mobile, email
    if data.get("full_name"):
        user.full_name = data["full_name"].strip()
    if "team_id" in data and data["team_id"] != user.team_id:
        team = _team(db, data["team_id"])
        changes["team"] = {
            "from": str(user.team_id) if user.team_id else None,
            "to": str(team.id) if team else None,
        }
        user.team = team
    if data.get("role") and data["role"] != user.role:
        if user.id == scope.user.id and data["role"] is not Role.ADMIN:
            raise unprocessable("ادمین نمی‌تواند نقش ادمین را از خودش بگیرد.")
        changes["role"] = {"from": user.role.value, "to": data["role"].value}
        user.role = data["role"]
        if user.role is not Role.SALES_MANAGER:
            # Only managers lead teams.
            db.execute(update(Team).where(Team.manager_id == user.id).values(manager_id=None))
    if changes:
        audit(db, "user.updated", scope.user.id, "user", user.id, changes, client_ip(request))
    db.commit()
    db.refresh(user)
    return _out(db, user)


@router.get("/users/{user_id}/open-items")
def user_open_items(user_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> OpenItems:
    require_admin(scope)
    return _open_items(db, user_id)


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: uuid.UUID,
    body: DeactivateIn,
    request: Request,
    db: DbDep,
    scope: ScopeDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> UserAdminOut:
    require_admin(scope)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="کاربر پیدا نشد.")
    if user.id == scope.user.id:
        raise unprocessable("نمی‌توانید حساب خودتان را غیرفعال کنید.")
    if not user.is_active:
        return _out(db, user)

    items = _open_items(db, user.id)
    target = None
    if body.transfer_to_id is not None:
        target = db.get(User, body.transfer_to_id)
        if target is None or not target.is_active or target.id == user.id:
            raise unprocessable("کاربر مقصد معتبر نیست.")
    elif items.total and not body.leave_open_items:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "این کاربر پرونده یا کار باز دارد؛ "
                "کاربر مقصد را انتخاب کنید یا ماندن آنها را تأیید کنید."
            ),
        )

    if target is not None:
        _transfer(db, scope, user, target)
        if items.total:
            notify(
                db,
                target.id,
                NotificationKind.RECORD_ASSIGNED,
                f"کارهای باز {user.full_name} به شما منتقل شد",
                f"transfer:{user.id}:{target.id}:{datetime.now(UTC).isoformat()}",
                body=(
                    f"{fa(items.leads)} مشتری احتمالی، {fa(items.customers)} مشتری، "
                    f"{fa(items.deals)} فروش باز و {fa(items.activities)} فعالیت"
                ),
                link="/activities",
            )
    user.is_active = False
    db.execute(update(Team).where(Team.manager_id == user.id).values(manager_id=None))
    audit(
        db,
        "user.deactivated",
        scope.user.id,
        "user",
        user.id,
        {"transferred_to": str(target.id) if target else None, "open_items": items.model_dump()},
        client_ip(request),
    )
    db.commit()
    # Spec 5: deactivation ends every session immediately.
    SessionService(db, redis, settings).revoke_all_for_user(user.id, "user_deactivated")
    db.refresh(user)
    return _out(db, user)


def _transfer(db: DbDep, scope: AccessScope, source: User, target: User) -> None:
    """Moves open records to ``target`` and records each owner change."""

    def history(entity_type: str, entity_id: uuid.UUID) -> None:
        db.add(
            OwnershipHistory(
                entity_type=entity_type,
                entity_id=entity_id,
                from_user_id=source.id,
                to_user_id=target.id,
                changed_by_id=scope.user.id,
                reason="غیرفعال‌شدن کاربر",
            )
        )

    for lead in db.scalars(
        select(Lead).where(
            Lead.owner_id == source.id,
            Lead.archived_at.is_(None),
            Lead.status.notin_([LeadStatus.CONVERTED, LeadStatus.DISQUALIFIED]),
        )
    ).unique():
        lead.owner_id, lead.owner = target.id, target
        history("lead", lead.id)
        emit(db, "record.assigned", "lead", lead.id, {"from": str(source.id), "to": str(target.id)})
    for customer in db.scalars(
        select(Customer).where(Customer.owner_id == source.id, Customer.archived_at.is_(None))
    ).unique():
        customer.owner_id, customer.owner = target.id, target
        history("customer", customer.id)
        emit(
            db,
            "record.assigned",
            "customer",
            customer.id,
            {"from": str(source.id), "to": str(target.id)},
        )
    for deal in db.scalars(
        select(Deal).where(
            Deal.owner_id == source.id, Deal.status == DealStatus.OPEN, Deal.archived_at.is_(None)
        )
    ).unique():
        deal.owner_id, deal.owner = target.id, target
        deal.version += 1
        history("deal", deal.id)
        emit(db, "record.assigned", "deal", deal.id, {"from": str(source.id), "to": str(target.id)})
    for activity in db.scalars(
        select(Activity).where(Activity.owner_id == source.id, Activity.status.in_(OPEN_STATUSES))
    ).unique():
        activity.owner_id, activity.owner = target.id, target
        activity.version += 1
        db.add(
            ActivityEvent(
                activity_id=activity.id,
                kind="reassigned",
                details={
                    "from": str(source.id),
                    "to": str(target.id),
                    "reason": "user_deactivated",
                },
                actor_id=scope.user.id,
            )
        )


@router.post("/users/{user_id}/reactivate")
def reactivate_user(
    user_id: uuid.UUID, request: Request, db: DbDep, scope: ScopeDep
) -> UserAdminOut:
    require_admin(scope)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="کاربر پیدا نشد.")
    if not user.is_active:
        user.is_active = True
        audit(db, "user.reactivated", scope.user.id, "user", user.id, None, client_ip(request))
        db.commit()
    return _out(db, user)


# -- teams -----------------------------------------------------------------------


def _team_out(db: DbDep, team: Team) -> TeamOut:
    out = TeamOut.model_validate(team)
    manager = db.get(User, team.manager_id) if team.manager_id else None
    out.manager = UserRef.model_validate(manager) if manager else None
    out.member_count = int(
        db.scalar(
            select(func.count(User.id)).where(User.team_id == team.id, User.is_active.is_(True))
        )
        or 0
    )
    return out


def _check_manager(
    db: DbDep, manager_id: uuid.UUID | None, team_id: uuid.UUID | None
) -> User | None:
    if manager_id is None:
        return None
    manager = db.get(User, manager_id)
    if manager is None or not manager.is_active or manager.role is not Role.SALES_MANAGER:
        raise unprocessable("مدیر تیم باید کاربر فعال با نقش مدیر فروش باشد.")
    other = db.scalar(
        select(Team).where(Team.manager_id == manager.id, Team.id != team_id)
        if team_id
        else select(Team).where(Team.manager_id == manager.id)
    )
    if other is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"این مدیر سرپرست تیم «{other.name}» است؛ هر مدیر فقط یک تیم دارد.",
        )
    return manager


@router.get("/teams")
def list_teams(db: DbDep, scope: ScopeDep) -> list[TeamOut]:
    query = select(Team).order_by(Team.is_active.desc(), Team.name)
    if scope.is_manager:
        query = query.where(Team.manager_id == scope.user.id)
    elif not scope.is_admin:
        raise _ADMIN_ONLY
    return [_team_out(db, t) for t in db.scalars(query)]


@router.post("/teams", status_code=status.HTTP_201_CREATED)
def create_team(body: TeamIn, request: Request, db: DbDep, scope: ScopeDep) -> TeamOut:
    require_admin(scope)
    if db.scalar(select(Team).where(func.lower(Team.name) == body.name.strip().lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="تیمی با این نام وجود دارد.")
    manager = _check_manager(db, body.manager_id, None)
    team = Team(
        name=body.name.strip(), is_active=body.is_active, manager_id=manager.id if manager else None
    )
    db.add(team)
    db.flush()
    if manager is not None and manager.team_id is None:
        manager.team_id = team.id
    audit(
        db, "team.created", scope.user.id, "team", team.id, {"name": team.name}, client_ip(request)
    )
    db.commit()
    return _team_out(db, team)


@router.patch("/teams/{team_id}")
def update_team(
    team_id: uuid.UUID, body: TeamIn, request: Request, db: DbDep, scope: ScopeDep
) -> TeamOut:
    require_admin(scope)
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="تیم پیدا نشد.")
    clash = db.scalar(
        select(Team).where(func.lower(Team.name) == body.name.strip().lower(), Team.id != team.id)
    )
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="تیمی با این نام وجود دارد.")
    manager = _check_manager(db, body.manager_id, team.id)
    changes = {
        k: v
        for k, v in {
            "name": body.name.strip() if body.name.strip() != team.name else None,
            "manager_id": str(body.manager_id) if body.manager_id != team.manager_id else None,
            "is_active": body.is_active if body.is_active != team.is_active else None,
        }.items()
        if v is not None
    }
    team.name = body.name.strip()
    team.manager_id = manager.id if manager else None
    team.is_active = body.is_active
    if manager is not None and manager.team_id != team.id:
        manager.team_id = team.id
    if changes:
        audit(db, "team.updated", scope.user.id, "team", team.id, changes, client_ip(request))
    db.commit()
    return _team_out(db, team)
