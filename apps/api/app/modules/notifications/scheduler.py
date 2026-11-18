"""Periodic jobs run by the worker (spec 7 "scheduler": due work is found in the
database, so nothing is lost when a process restarts).

Only one worker runs a tick at a time (Postgres advisory lock), and every
notification has a dedupe key, so overlapping or repeated ticks are harmless.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.activities.models import OPEN_STATUSES, Activity
from app.modules.identity.models import User
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import ACTIVITY_LABELS, DIGEST_HOUR, fa, notify

ADVISORY_LOCK = 0x43524D5F534348  # "CRM_SCH"
# A reminder older than this (worker down for a long time) is dropped, not sent late.
STALE_AFTER = timedelta(hours=12)


def _link(activity: Activity) -> str:
    if activity.deal_id:
        return f"/deals/{activity.deal_id}"
    if activity.customer_id:
        return f"/customers/{activity.customer_id}"
    if activity.lead_id:
        return f"/leads/{activity.lead_id}"
    return "/activities"


def send_reminders(db: Session, now: datetime) -> int:
    due = db.scalars(
        select(Activity)
        .where(
            Activity.status.in_(OPEN_STATUSES),
            Activity.remind_at.is_not(None),
            Activity.remind_at <= now,
            Activity.reminded_at.is_(None),
        )
        .order_by(Activity.remind_at)
        .limit(500)
        .with_for_update(skip_locked=True, of=Activity)
    ).unique()
    tz = ZoneInfo(get_settings().timezone)
    sent = 0
    for activity in due:
        activity.reminded_at = now
        assert activity.remind_at is not None  # noqa: S101 - filtered above
        if now - activity.remind_at > STALE_AFTER:
            continue
        when = (
            fa(activity.start_at.astimezone(tz).strftime("%H:%M")) if activity.start_at else "امروز"
        )
        subject = activity.deal or activity.customer or activity.lead
        about = getattr(subject, "title", None) or getattr(subject, "full_name", None)
        notify(
            db,
            activity.owner_id,
            NotificationKind.ACTIVITY_REMINDER,
            f"یادآوری {ACTIVITY_LABELS.get(activity.type.value, 'فعالیت')}: {activity.title}",
            f"reminder:{activity.id}:{activity.remind_at.isoformat()}",
            body=f"زمان: {when}" + (f" — {about}" if about else ""),
            link=_link(activity),
        )
        sent += 1
    return sent


def send_daily_digest(db: Session, now: datetime) -> int:
    """Once a day after 08:00 local: today's and overdue work, for anyone who has some."""
    tz = ZoneInfo(get_settings().timezone)
    local = now.astimezone(tz)
    if local.hour < DIGEST_HOUR:
        return 0
    today = local.date()
    rows = db.execute(
        select(
            Activity.owner_id,
            func.count().filter(Activity.due_date == today),
            func.count().filter(Activity.due_date < today),
        )
        .join(User, User.id == Activity.owner_id)
        .where(
            Activity.status.in_(OPEN_STATUSES), Activity.due_date <= today, User.is_active.is_(True)
        )
        .group_by(Activity.owner_id)
    ).all()
    for owner_id, today_count, overdue_count in rows:
        parts = []
        if today_count:
            parts.append(f"{fa(today_count)} کار امروز")
        if overdue_count:
            parts.append(f"{fa(overdue_count)} کار معوق")
        notify(
            db,
            owner_id,
            NotificationKind.DAILY_DIGEST,
            "برنامه امروز: " + " و ".join(parts),
            f"digest:{owner_id}:{today.isoformat()}",
            link="/activities",
        )
    return len(rows)


def tick(db: Session, now: datetime | None = None) -> bool:
    """One scheduler pass. Returns False when another worker holds the lock."""
    now = now or datetime.now(UTC)
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK}):
        db.rollback()
        return False
    send_reminders(db, now)
    send_daily_digest(db, now)
    db.commit()
    return True
