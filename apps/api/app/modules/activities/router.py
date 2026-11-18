import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.modules.activities.models import (
    OPEN_STATUSES,
    Activity,
    ActivityEvent,
    ActivityStatus,
    ActivityType,
)
from app.modules.activities.schemas import (
    ActivityCreate,
    ActivityOut,
    ActivityUpdate,
    CancelIn,
    CompleteIn,
    EventOut,
    Overlap,
    PostponeIn,
    StartIn,
    Workload,
)
from app.modules.activities.service import (
    CONTACT_TYPES,
    can_view_schedule,
    load_for_change,
    out,
    overlaps,
    record_event,
    refresh_reminder,
    require_access,
    require_open,
    resolve_links,
    schedule_snapshot,
    start_at_for,
    today,
    touch_records,
    tz,
    visible_filter,
)
from app.modules.auth.deps import DbDep, require_csrf
from app.modules.crm.common import ScopeDep, paginate, resolve_owner, unprocessable
from app.modules.crm.schemas import Page, UserRef
from app.modules.identity.models import User
from app.modules.notifications.service import activity_assigned

router = APIRouter(prefix="/activities", tags=["activities"], dependencies=[Depends(require_csrf)])

Range = Literal["overdue", "today", "tomorrow", "week", "custom"]
StatusFilter = Literal["open", "done", "canceled", "all"]

_FORBIDDEN_SCHEDULE = HTTPException(
    status.HTTP_403_FORBIDDEN, detail="مشاهده برنامه این کاربر مجاز نیست."
)


def end_of_week(day: date) -> date:
    """The Iranian week ends on Friday (Python weekday 4)."""
    return day + timedelta(days=(4 - day.weekday()) % 7)


@router.get("")
def list_activities(
    db: DbDep,
    scope: ScopeDep,
    range_: Annotated[Range | None, Query(alias="range")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_: Annotated[StatusFilter, Query(alias="status")] = "open",
    type_: Annotated[ActivityType | None, Query(alias="type")] = None,
    owner_id: uuid.UUID | None = None,
    mine: bool = False,
    deal_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[ActivityOut]:
    """Activities across all files the user may see (spec 4.2), upcoming ones first."""
    on = today()
    query = select(Activity).where(visible_filter(scope))
    if status_ == "open":
        query = query.where(Activity.status.in_(OPEN_STATUSES))
    elif status_ == "done":
        query = query.where(Activity.status == ActivityStatus.DONE)
    elif status_ == "canceled":
        query = query.where(Activity.status == ActivityStatus.CANCELED)

    if range_ == "overdue":
        query = query.where(Activity.status.in_(OPEN_STATUSES), Activity.due_date < on)
    elif range_ == "today":
        query = query.where(Activity.due_date == on)
    elif range_ == "tomorrow":
        query = query.where(Activity.due_date == on + timedelta(days=1))
    elif range_ == "week":
        query = query.where(Activity.due_date >= on, Activity.due_date <= end_of_week(on))
    elif range_ == "custom":
        if date_from and date_to and date_from > date_to:
            raise unprocessable("تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد.")
        if date_from:
            query = query.where(Activity.due_date >= date_from)
        if date_to:
            query = query.where(Activity.due_date <= date_to)

    if type_:
        query = query.where(Activity.type == type_)
    if owner_id:
        query = query.where(Activity.owner_id == owner_id)
    if mine:
        query = query.where(Activity.owner_id == scope.user.id)
    if deal_id:
        query = query.where(Activity.deal_id == deal_id)
    if customer_id:
        query = query.where(Activity.customer_id == customer_id)
    if lead_id:
        query = query.where(Activity.lead_id == lead_id)

    if status_ == "done":
        query = query.order_by(Activity.completed_at.desc(), Activity.id)
    else:
        query = query.order_by(
            Activity.due_date,
            Activity.start_at.asc().nulls_first(),
            Activity.created_at,
            Activity.id,
        )
    rows, total = paginate(db, query, page, page_size)
    return Page[ActivityOut](
        items=[out(a, on) for a in rows], total=total, page=page, page_size=page_size
    )


@router.get("/calendar")
def calendar(
    db: DbDep,
    scope: ScopeDep,
    date_from: date,
    date_to: date,
    owner_id: uuid.UUID | None = None,
    mine: bool = False,
    type_: Annotated[ActivityType | None, Query(alias="type")] = None,
) -> list[ActivityOut]:
    """Non-cancelled activities between two dates for the calendar views."""
    if date_from > date_to or (date_to - date_from).days > 62:
        raise unprocessable("بازه تقویم معتبر نیست.")
    query = (
        select(Activity)
        .where(
            visible_filter(scope),
            Activity.due_date >= date_from,
            Activity.due_date <= date_to,
            Activity.status != ActivityStatus.CANCELED,
        )
        .order_by(Activity.due_date, Activity.start_at.asc().nulls_first(), Activity.id)
        .limit(1000)
    )
    if owner_id:
        query = query.where(Activity.owner_id == owner_id)
    if mine:
        query = query.where(Activity.owner_id == scope.user.id)
    if type_:
        query = query.where(Activity.type == type_)
    on = today()
    return [out(a, on) for a in db.scalars(query)]


@router.get("/day")
def owner_day(db: DbDep, scope: ScopeDep, owner_id: uuid.UUID, day: date) -> list[ActivityOut]:
    """One person's schedule for a day, shown beside the activity form (spec 4.2)."""
    if not can_view_schedule(scope, owner_id):
        raise _FORBIDDEN_SCHEDULE
    rows = db.scalars(
        select(Activity)
        .where(
            Activity.owner_id == owner_id,
            Activity.due_date == day,
            Activity.status != ActivityStatus.CANCELED,
        )
        .order_by(Activity.start_at.asc().nulls_first(), Activity.id)
    )
    on = today()
    return [out(a, on) for a in rows]


@router.get("/workload")
def workload(db: DbDep, scope: ScopeDep, owner_id: uuid.UUID | None = None) -> Workload:
    """Today's open count, timed minutes and overlaps, plus everything overdue (spec 4.2)."""
    owner = scope.user if owner_id is None else db.get(User, owner_id)
    if owner is None or not can_view_schedule(scope, owner.id):
        raise _FORBIDDEN_SCHEDULE
    on = today()
    todays = list(
        db.scalars(
            select(Activity).where(
                Activity.owner_id == owner.id,
                Activity.due_date == on,
                Activity.status.in_(OPEN_STATUSES),
            )
        )
    )
    overdue = db.scalars(
        select(Activity.id).where(
            Activity.owner_id == owner.id,
            Activity.due_date < on,
            Activity.status.in_(OPEN_STATUSES),
        )
    ).all()
    return Workload(
        date=on,
        owner=UserRef.model_validate(owner),
        open_count=len(todays),
        overdue_count=len(overdue),
        timed_minutes=sum(a.duration_minutes or 0 for a in todays if a.start_at is not None),
        overlaps=[Overlap(first=a, second=b) for a, b in overlaps(todays)],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_activity(body: ActivityCreate, db: DbDep, scope: ScopeDep) -> ActivityOut:
    owner = resolve_owner(db, scope, body.owner_id)
    lead, customer, deal = resolve_links(db, scope, body.lead_id, body.customer_id, body.deal_id)
    if body.duration_minutes and not body.start_time:
        raise unprocessable("برای تعیین مدت، ساعت شروع لازم است.")
    activity = Activity(
        type=body.type,
        title=body.title.strip(),
        description=body.description,
        owner=owner,
        owner_id=owner.id,
        created_by_id=scope.user.id,
        due_date=body.due_date,
        start_at=start_at_for(body.due_date, body.start_time),
        duration_minutes=body.duration_minutes,
        priority=body.priority,
        reminder_minutes=body.reminder_minutes,
        lead=lead,
        customer=customer,
        deal=deal,
    )
    refresh_reminder(activity)
    db.add(activity)
    db.flush()
    record_event(db, activity, scope, "created", schedule_snapshot(activity))
    if owner.id != scope.user.id:
        activity_assigned(
            db, owner.id, scope.user.full_name, activity.id, activity.type.value, activity.title
        )
    db.commit()
    db.refresh(activity)
    return out(activity)


@router.get("/{activity_id}")
def get_activity(activity_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> ActivityOut:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="فعالیت پیدا نشد.")
    require_access(scope, activity)
    return out(activity)


@router.get("/{activity_id}/events")
def activity_events(activity_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> list[EventOut]:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="فعالیت پیدا نشد.")
    require_access(scope, activity)
    rows = db.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.activity_id == activity.id)
        .order_by(ActivityEvent.at, ActivityEvent.id)
    )
    return [EventOut.model_validate(e) for e in rows]


@router.patch("/{activity_id}")
def update_activity(
    activity_id: uuid.UUID, body: ActivityUpdate, db: DbDep, scope: ScopeDep
) -> ActivityOut:
    activity = load_for_change(db, scope, activity_id, body.version)
    require_open(activity)
    data = body.model_dump(exclude_unset=True, exclude={"version"})

    if "owner_id" in data and data["owner_id"] not in (None, activity.owner_id):
        new_owner = resolve_owner(db, scope, data["owner_id"])
        record_event(
            db,
            activity,
            scope,
            "reassigned",
            {"from": str(activity.owner_id), "to": str(new_owner.id)},
        )
        activity.owner_id, activity.owner = new_owner.id, new_owner
        if new_owner.id != scope.user.id:
            activity_assigned(
                db,
                new_owner.id,
                scope.user.full_name,
                activity.id,
                activity.type.value,
                activity.title,
            )
    data.pop("owner_id", None)

    if {"due_date", "start_time", "duration_minutes"} & data.keys():
        before = schedule_snapshot(activity)
        due = data.pop("due_date", None) or activity.due_date
        if "start_time" in data:
            start_time = data.pop("start_time")
        else:
            current = activity.start_at
            start_time = current.astimezone(tz()).strftime("%H:%M") if current else None
        activity.due_date = due
        activity.start_at = start_at_for(due, start_time)
        if "duration_minutes" in data:
            activity.duration_minutes = data.pop("duration_minutes")
        if activity.duration_minutes and activity.start_at is None:
            raise unprocessable("برای تعیین مدت، ساعت شروع لازم است.")
        after = schedule_snapshot(activity)
        if after != before:
            record_event(db, activity, scope, "rescheduled", {"from": before, "to": after})

    for key in ("title", "type", "priority"):
        if data.get(key) is None:
            data.pop(key, None)
    for key, value in data.items():
        setattr(activity, key, value)
    refresh_reminder(activity)
    activity.version += 1
    db.commit()
    db.refresh(activity)
    return out(activity)


@router.post("/{activity_id}/start")
def start_activity(
    activity_id: uuid.UUID, body: StartIn, db: DbDep, scope: ScopeDep
) -> ActivityOut:
    activity = load_for_change(db, scope, activity_id, body.version)
    if activity.status is not ActivityStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این فعالیت در وضعیت انتظار نیست.")
    activity.status = ActivityStatus.IN_PROGRESS
    activity.version += 1
    record_event(db, activity, scope, "started")
    db.commit()
    return out(activity)


@router.post("/{activity_id}/complete")
def complete_activity(
    activity_id: uuid.UUID, body: CompleteIn, db: DbDep, scope: ScopeDep
) -> ActivityOut:
    """Completion with the result. The row lock and version check mean two people
    completing at once cannot record it twice (spec 4.2)."""
    activity = load_for_change(db, scope, activity_id, body.version)
    require_open(activity)
    now = datetime.now(UTC)
    activity.status = ActivityStatus.DONE
    activity.outcome = body.outcome
    activity.completed_at = now
    activity.completed_by_id = scope.user.id
    activity.version += 1
    touch_records(
        now, activity.deal, activity.customer, activity.lead, contact=activity.type in CONTACT_TYPES
    )
    record_event(db, activity, scope, "completed")
    db.commit()
    db.refresh(activity)
    return out(activity)


@router.post("/{activity_id}/postpone")
def postpone_activity(
    activity_id: uuid.UUID, body: PostponeIn, db: DbDep, scope: ScopeDep
) -> ActivityOut:
    activity = load_for_change(db, scope, activity_id, body.version)
    require_open(activity)
    before = schedule_snapshot(activity)
    activity.due_date = body.due_date
    activity.start_at = start_at_for(body.due_date, body.start_time)
    activity.duration_minutes = body.duration_minutes if body.start_time else None
    refresh_reminder(activity)
    activity.version += 1
    record_event(
        db,
        activity,
        scope,
        "postponed",
        {"from": before, "to": schedule_snapshot(activity), "reason": body.reason},
    )
    db.commit()
    db.refresh(activity)
    return out(activity)


@router.post("/{activity_id}/cancel")
def cancel_activity(
    activity_id: uuid.UUID, body: CancelIn, db: DbDep, scope: ScopeDep
) -> ActivityOut:
    activity = load_for_change(db, scope, activity_id, body.version)
    require_open(activity)
    activity.status = ActivityStatus.CANCELED
    activity.cancel_reason = body.reason.strip()
    activity.version += 1
    record_event(db, activity, scope, "canceled", {"reason": activity.cancel_reason})
    db.commit()
    db.refresh(activity)
    return out(activity)
