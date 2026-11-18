"""Team work queues (spec 4.6 and 5; TeamTaskAssignment in section 9).

* Work for an operational (finance) team waits in the team's queue with no one
  responsible. A member claims it, or the team's manager (or an admin) assigns it to a
  member; either way it becomes an ordinary activity of that person.
* Claiming is one conditional UPDATE on the task's status, so when two members claim at
  the same moment exactly one gets it and the other is told it is taken.
* Who sees a queue: the team's active members, its manager, and admins. They see the
  deal details the task needs (amounts, payments, balance, the contact's phone and
  email) — nothing else about the customer or the sales pipeline.
* If the team is inactive or has no active member, nothing is queued: the caller (an
  automation) fails with a clear error, which is reported to the rule's author.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.modules.activities.models import (
    Activity,
    ActivityEvent,
    ActivityType,
    Priority,
    TeamTask,
    TeamTaskStatus,
)
from app.modules.activities.schemas import ActivityOut, LinkRef
from app.modules.activities.service import out
from app.modules.auth.deps import DbDep, require_csrf
from app.modules.crm.access import AccessScope
from app.modules.crm.common import ScopeDep, paginate
from app.modules.crm.models import Customer, Lead
from app.modules.crm.schemas import Page, UserRef
from app.modules.identity.models import Role, Team, TeamKind, User
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import activity_assigned, notify
from app.modules.sales.models import Deal

router = APIRouter(prefix="/team-tasks", tags=["team-tasks"], dependencies=[Depends(require_csrf)])

QUEUE_LINK = "/team-queue"


class QueueError(Exception):
    """The team cannot take work (inactive, or no active member)."""


# -- who may do what -----------------------------------------------------------------


def queue_team_ids(db: Session, user: User) -> list[uuid.UUID]:
    """Finance teams whose queue the user may open."""
    query = select(Team.id).where(Team.kind == TeamKind.FINANCE).order_by(Team.name)
    if user.role is Role.ADMIN:
        return list(db.scalars(query))
    mine = [Team.manager_id == user.id]
    if user.team_id is not None:
        mine.append(Team.id == user.team_id)
    return list(db.scalars(query.where(Team.is_active.is_(True), or_(*mine))))


def can_manage(user: User, team: Team) -> bool:
    return user.role is Role.ADMIN or team.manager_id == user.id


def is_member(user: User, team: Team) -> bool:
    return user.is_active and user.team_id == team.id


def active_members(db: Session, team: Team) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.team_id == team.id, User.is_active.is_(True))
            .order_by(User.full_name)
        )
    )


# -- creating and assigning ------------------------------------------------------------


def queue_task(
    db: Session,
    *,
    team: Team,
    type_: ActivityType,
    title: str,
    description: str | None,
    due_date: date,
    created_by: User,
    lead: Lead | None = None,
    customer: Customer | None = None,
    deal: Deal | None = None,
    source: dict[str, Any] | None = None,
) -> TeamTask:
    """Puts work in a team's queue and tells the members and the manager."""
    if team.kind is not TeamKind.FINANCE:
        raise QueueError(f"«{team.name}» تیم عملیاتی (مالی) نیست و صف کار ندارد.")
    members = active_members(db, team)
    if not team.is_active or not members:
        raise QueueError(f"تیم «{team.name}» غیرفعال است یا عضو فعالی ندارد.")
    task = TeamTask(
        team_id=team.id,
        team=team,
        type=type_,
        title=title[:200],
        description=description,
        due_date=due_date,
        lead=lead,
        customer=customer,
        deal=deal,
        created_by_id=created_by.id,
        source=source,
    )
    db.add(task)
    db.flush()
    recipients = {u.id for u in members}
    if team.manager_id:
        recipients.add(team.manager_id)
    for user_id in recipients:
        notify(
            db,
            user_id,
            NotificationKind.TEAM_TASK,
            f"کار جدید در صف «{team.name}»: {task.title}",
            f"team-task:{task.id}:{user_id}",
            body="یکی از اعضا می‌تواند آن را بردارد یا مدیر تیم واگذار می‌کند.",
            link=QUEUE_LINK,
        )
    return task


def _take(db: Session, task: TeamTask, assignee: User, actor: User) -> Activity:
    """Atomically moves an open task to ``assignee`` and creates their activity."""
    now = datetime.now(UTC)
    taken = db.execute(
        update(TeamTask)
        .where(TeamTask.id == task.id, TeamTask.status == TeamTaskStatus.OPEN)
        .values(
            status=TeamTaskStatus.ASSIGNED,
            assigned_to_id=assignee.id,
            assigned_by_id=actor.id,
            assigned_at=now,
            updated_at=now,
        )
        .returning(TeamTask.id)
    ).scalar()
    if taken is None:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="این کار را پیش‌تر عضو دیگری برداشته یا لغو شده است."
        )
    db.refresh(task)
    activity = Activity(
        type=task.type,
        title=task.title,
        description=task.description,
        owner_id=assignee.id,
        owner=assignee,
        created_by_id=task.created_by_id,
        due_date=task.due_date,
        priority=task.priority,
        lead_id=task.lead_id,
        customer_id=task.customer_id,
        deal_id=task.deal_id,
        team_task_id=task.id,
    )
    db.add(activity)
    db.flush()
    db.add(
        ActivityEvent(
            activity_id=activity.id,
            kind="created",
            details={
                "team_task": str(task.id),
                "team": task.team.name,
                "via": "claimed" if assignee.id == actor.id else "assigned",
            },
            actor_id=actor.id,
        )
    )
    if assignee.id != actor.id:
        activity_assigned(
            db, assignee.id, actor.full_name, activity.id, activity.type.value, activity.title
        )
    return activity


# -- views -----------------------------------------------------------------------------


class TeamRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class TaskContext(BaseModel):
    """What a finance member needs about the deal behind a task, and nothing more."""

    contact_name: str | None = None
    mobile: str | None = None
    phone: str | None = None
    email: str | None = None
    deal_title: str | None = None
    deal_status: str | None = None
    stage: str | None = None
    amount: int | None = None
    contract_amount: int | None = None
    contract_date: date | None = None
    paid: int = 0
    balance: int | None = None


class TeamTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team: TeamRef
    type: ActivityType
    title: str
    description: str | None
    due_date: date
    priority: Priority
    status: TeamTaskStatus
    created_at: datetime
    created_by: UserRef
    assigned_to: UserRef | None
    assigned_at: datetime | None
    cancel_reason: str | None
    lead: LinkRef | None = None
    customer: LinkRef | None = None
    deal: LinkRef | None = None
    activity_id: uuid.UUID | None = None
    context: TaskContext | None = None
    can_manage: bool = False
    can_claim: bool = False


def _contexts(db: Session, tasks: list[TeamTask]) -> dict[uuid.UUID, TaskContext]:
    from app.modules.sales.deals import payment_totals  # deals imports this package

    paid = payment_totals(db, [t.deal_id for t in tasks if t.deal_id])
    result = {}
    for task in tasks:
        contact = task.customer or (task.deal.customer if task.deal else None) or task.lead
        ctx = TaskContext()
        if contact is not None:
            ctx.contact_name = contact.full_name
            ctx.mobile = contact.mobile
            ctx.email = contact.email
            ctx.phone = getattr(contact, "phone", None)
        if task.deal is not None:
            deal = task.deal
            ctx.deal_title = deal.title
            ctx.deal_status = deal.status.value
            ctx.stage = deal.stage.name
            ctx.amount = deal.amount
            ctx.contract_amount = deal.contract_amount
            ctx.contract_date = deal.contract_date
            ctx.paid = paid.get(deal.id, 0)
            expected = deal.contract_amount if deal.contract_amount is not None else deal.amount
            ctx.balance = max(expected - ctx.paid, 0) if expected is not None else None
        result[task.id] = ctx
    return result


def _views(db: Session, user: User, tasks: list[TeamTask]) -> list[TeamTaskOut]:
    contexts = _contexts(db, tasks)
    rows = db.execute(
        select(Activity.team_task_id, Activity.id).where(
            Activity.team_task_id.in_([t.id for t in tasks])
        )
    )
    activities = {task_id: activity_id for task_id, activity_id in rows}
    views = []
    for task in tasks:
        view = TeamTaskOut.model_validate(task)
        view.context = contexts[task.id]
        view.activity_id = activities.get(task.id)
        open_ = task.status is TeamTaskStatus.OPEN
        view.can_manage = open_ and can_manage(user, task.team)
        view.can_claim = open_ and is_member(user, task.team)
        views.append(view)
    return views


def _load(db: Session, scope: AccessScope, task_id: uuid.UUID, *, lock: bool = False) -> TeamTask:
    query = select(TeamTask).where(TeamTask.id == task_id)
    if lock:
        query = query.with_for_update(of=TeamTask)
    task = db.scalar(query)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="کار پیدا نشد.")
    if task.team_id in queue_team_ids(db, scope.user):
        return task
    # The person now responsible keeps seeing the task behind their activity.
    if task.assigned_to_id == scope.user.id:
        return task
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="کار پیدا نشد.")


# -- endpoints -----------------------------------------------------------------------------


@router.get("/targets")
def targets(db: DbDep, scope: ScopeDep) -> list[TeamRef]:
    """Teams an automation may queue work for (managers and admins)."""
    if not (scope.is_admin or scope.is_manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="فقط مدیر و ادمین.")
    rows = db.scalars(
        select(Team)
        .where(Team.kind == TeamKind.FINANCE, Team.is_active.is_(True))
        .order_by(Team.name)
    )
    return [TeamRef.model_validate(t) for t in rows]


@router.get("")
def list_tasks(
    db: DbDep,
    scope: ScopeDep,
    status_: Annotated[Literal["open", "assigned", "canceled"], Query(alias="status")] = "open",
    team_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[TeamTaskOut]:
    teams = queue_team_ids(db, scope.user)
    if team_id is not None:
        teams = [t for t in teams if t == team_id]
    query = (
        select(TeamTask)
        .where(TeamTask.team_id.in_(teams), TeamTask.status == TeamTaskStatus(status_))
        .order_by(
            TeamTask.due_date if status_ == "open" else TeamTask.updated_at.desc(),
            TeamTask.created_at,
            TeamTask.id,
        )
    )
    rows, total = paginate(db, query, page, page_size)
    return Page[TeamTaskOut](
        items=_views(db, scope.user, list(rows)), total=total, page=page, page_size=page_size
    )


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> TeamTaskOut:
    return _views(db, scope.user, [_load(db, scope, task_id)])[0]


@router.get("/{task_id}/members")
def task_members(task_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> list[UserRef]:
    """Who the manager can assign this task to."""
    task = _load(db, scope, task_id)
    if not can_manage(scope.user, task.team):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="واگذاری با مدیر همین تیم است.")
    return [UserRef.model_validate(u) for u in active_members(db, task.team)]


@router.post("/{task_id}/claim")
def claim(task_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> ActivityOut:
    task = _load(db, scope, task_id)
    if not is_member(scope.user, task.team):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="فقط اعضای همین تیم می‌توانند کار را بردارند."
        )
    activity = _take(db, task, scope.user, scope.user)
    db.commit()
    db.refresh(activity)
    return out(activity)


class AssignIn(BaseModel):
    user_id: uuid.UUID


@router.post("/{task_id}/assign")
def assign(task_id: uuid.UUID, body: AssignIn, db: DbDep, scope: ScopeDep) -> ActivityOut:
    task = _load(db, scope, task_id)
    if not can_manage(scope.user, task.team):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="واگذاری با مدیر همین تیم است.")
    assignee = db.get(User, body.user_id)
    if assignee is None or not is_member(assignee, task.team):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="این کاربر عضو فعال این تیم نیست."
        )
    activity = _take(db, task, assignee, scope.user)
    db.commit()
    db.refresh(activity)
    return out(activity)


class CancelIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


@router.post("/{task_id}/cancel")
def cancel(task_id: uuid.UUID, body: CancelIn, db: DbDep, scope: ScopeDep) -> TeamTaskOut:
    task = _load(db, scope, task_id, lock=True)
    if not can_manage(scope.user, task.team):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="لغو با مدیر همین تیم است.")
    if task.status is not TeamTaskStatus.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این کار دیگر در صف نیست.")
    task.status = TeamTaskStatus.CANCELED
    task.cancel_reason = body.reason.strip()
    db.commit()
    return _views(db, scope.user, [task])[0]
