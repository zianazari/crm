"""Shared activity logic: time handling, visibility, links, events and output."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.activities.models import (
    OPEN_STATUSES,
    Activity,
    ActivityEvent,
    ActivityType,
)
from app.modules.activities.schemas import ActivityBrief, ActivityOut
from app.modules.crm.access import FORBIDDEN, AccessScope
from app.modules.crm.common import unprocessable
from app.modules.crm.models import Customer, Lead
from app.modules.sales.models import Deal

DEFAULT_DURATION = 30  # minutes assumed for overlap checks when none is given


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def today() -> date:
    return datetime.now(tz()).date()


def start_at_for(due_date: date, start_time: str | None) -> datetime | None:
    if start_time is None:
        return None
    hours, minutes = (int(x) for x in start_time.split(":"))
    return datetime.combine(due_date, time(hours, minutes), tz()).astimezone(UTC)


def is_overdue(activity: Activity, on: date) -> bool:
    return activity.status in OPEN_STATUSES and activity.due_date < on


# -- visibility ------------------------------------------------------------


def visible_filter(scope: AccessScope) -> ColumnElement[bool]:
    """Activities a user may see: assigned to someone in their scope, or linked to a
    lead, customer or deal they see in full."""
    ids = scope.owner_ids()
    if ids is None:
        return true()
    return or_(
        Activity.owner_id.in_(ids),
        Activity.deal_id.in_(select(Deal.id).where(Deal.owner_id.in_(ids))),
        Activity.customer_id.in_(select(Customer.id).where(Customer.owner_id.in_(ids))),
        Activity.lead_id.in_(select(Lead.id).where(Lead.owner_id.in_(ids))),
    )


def can_access(scope: AccessScope, activity: Activity) -> bool:
    if scope.has_full_access(activity.owner_id):
        return True
    return any(
        record is not None and scope.has_full_access(record.owner_id)
        for record in (activity.deal, activity.customer, activity.lead)
    )


def require_access(scope: AccessScope, activity: Activity) -> None:
    if not can_access(scope, activity):
        raise FORBIDDEN


def can_view_schedule(scope: AccessScope, owner_id: uuid.UUID) -> bool:
    """Whose calendar a user may look at: their own, their team's (manager), everyone (admin)."""
    ids = scope.owner_ids()
    return ids is None or owner_id in ids


# -- links -----------------------------------------------------------------


def resolve_links(
    db: Session,
    scope: AccessScope,
    lead_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    deal_id: uuid.UUID | None,
) -> tuple[Lead | None, Customer | None, Deal | None]:
    """Validates the records an activity or note is attached to. A deal brings its
    customer along so the customer's file shows the activity too."""
    deal = db.get(Deal, deal_id) if deal_id else None
    if deal_id and (deal is None or deal.archived_at is not None):
        raise unprocessable("فروش انتخاب‌شده معتبر نیست.")
    if deal is not None:
        scope.require_full(deal.owner_id)
        if customer_id and customer_id != deal.customer_id:
            raise unprocessable("مشتری با فروش انتخاب‌شده هم‌خوانی ندارد.")
        customer_id = deal.customer_id

    customer = db.get(Customer, customer_id) if customer_id else None
    if customer_id and (customer is None or customer.archived_at is not None):
        raise unprocessable("مشتری انتخاب‌شده معتبر نیست.")
    if customer is not None and deal is None:
        scope.require_full(customer.owner_id)

    lead = db.get(Lead, lead_id) if lead_id else None
    if lead_id and (lead is None or lead.archived_at is not None):
        raise unprocessable("مشتری احتمالی انتخاب‌شده معتبر نیست.")
    if lead is not None:
        scope.require_full(lead.owner_id)
    return lead, customer, deal


def touch_records(
    at: datetime,
    deal: Deal | None,
    customer: Customer | None,
    lead: Lead | None,
    *,
    contact: bool,
) -> None:
    """Keeps 'last activity' on the linked records current (spec 4.1, 4.3). A lead's
    last contact moves only for calls and meetings."""
    if deal is not None:
        deal.last_activity_at = at
    if customer is not None:
        customer.last_activity_at = at
    if lead is not None and contact:
        lead.last_contacted_at = at


CONTACT_TYPES = (ActivityType.CALL, ActivityType.MEETING)


# -- events & output ---------------------------------------------------------


def record_event(
    db: Session,
    activity: Activity,
    scope: AccessScope,
    kind: str,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        ActivityEvent(activity_id=activity.id, kind=kind, details=details, actor_id=scope.user.id)
    )


def schedule_snapshot(activity: Activity) -> dict[str, Any]:
    return {
        "due_date": activity.due_date.isoformat(),
        "start_at": activity.start_at.isoformat() if activity.start_at else None,
        "duration_minutes": activity.duration_minutes,
    }


def load_for_change(
    db: Session, scope: AccessScope, activity_id: uuid.UUID, version: int
) -> Activity:
    activity = db.scalar(
        select(Activity).where(Activity.id == activity_id).with_for_update(of=Activity)
    )
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="فعالیت پیدا نشد.")
    require_access(scope, activity)
    if activity.version != version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="این فعالیت هم‌زمان توسط کاربر دیگری تغییر کرده است. صفحه را به‌روز کنید.",
        )
    return activity


def require_open(activity: Activity) -> None:
    if activity.status not in OPEN_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="این فعالیت قبلاً انجام یا لغو شده است.",
        )


def out(activity: Activity, on: date | None = None) -> ActivityOut:
    result = ActivityOut.model_validate(activity)
    result.overdue = is_overdue(activity, on or today())
    return result


def next_activities(db: Session, deal_ids: list[uuid.UUID]) -> dict[uuid.UUID, ActivityBrief]:
    """Earliest open activity per deal, for the board's next-action indicator."""
    if not deal_ids:
        return {}
    rows = db.scalars(
        select(Activity)
        .where(Activity.deal_id.in_(deal_ids), Activity.status.in_(OPEN_STATUSES))
        .order_by(Activity.due_date, Activity.start_at.asc().nulls_last(), Activity.created_at)
    )
    on = today()
    result: dict[uuid.UUID, ActivityBrief] = {}
    for activity in rows:
        if activity.deal_id is not None and activity.deal_id not in result:
            result[activity.deal_id] = ActivityBrief(
                id=activity.id,
                type=activity.type,
                title=activity.title,
                due_date=activity.due_date,
                start_at=activity.start_at,
                overdue=is_overdue(activity, on),
            )
    return result


def overlaps(activities: list[Activity]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    timed = sorted(
        (a for a in activities if a.start_at is not None and a.status in OPEN_STATUSES),
        key=lambda a: a.start_at or datetime.min.replace(tzinfo=UTC),
    )
    pairs = []
    for i, first in enumerate(timed):
        assert first.start_at is not None  # noqa: S101 - filtered above
        first_end = first.start_at + timedelta(minutes=first.duration_minutes or DEFAULT_DURATION)
        for second in timed[i + 1 :]:
            assert second.start_at is not None  # noqa: S101
            if second.start_at >= first_end:
                break
            pairs.append((first.id, second.id))
    return pairs
