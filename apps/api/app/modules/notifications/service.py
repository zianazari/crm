"""Creating notifications. Every function adds to the caller's transaction."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.notifications.models import Notification, NotificationKind

UNTIMED_REMINDER_HOUR = 9  # date-only activities are reminded relative to 09:00 local
DIGEST_HOUR = 8

ACTIVITY_LABELS = {"call": "تماس", "meeting": "جلسه", "follow_up": "پیگیری", "task": "وظیفه"}
RECORD_LABELS = {"lead": "مشتری احتمالی", "customer": "مشتری", "deal": "فروش"}
RECORD_PATHS = {"lead": "/leads", "customer": "/customers", "deal": "/deals"}


def fa(value: int | str) -> str:
    """Persian digits, as everywhere else in the interface."""
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def notify(
    db: Session,
    user_id: uuid.UUID,
    kind: NotificationKind,
    title: str,
    dedupe_key: str,
    body: str | None = None,
    link: str | None = None,
) -> None:
    """Idempotent: a second call with the same ``dedupe_key`` does nothing."""
    db.execute(
        insert(Notification)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            kind=kind,
            title=title[:200],
            body=body[:500] if body else None,
            link=link,
            dedupe_key=dedupe_key[:200],
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )


def remind_at(
    reminder_minutes: int | None, start_at: datetime | None, due_date: date
) -> datetime | None:
    if reminder_minutes is None:
        return None
    tz = ZoneInfo(get_settings().timezone)
    anchor = start_at or datetime.combine(due_date, time(UNTIMED_REMINDER_HOUR), tz)
    return (anchor - timedelta(minutes=reminder_minutes)).astimezone(UTC)


def activity_assigned(
    db: Session, user_id: uuid.UUID, actor_name: str, activity_id: uuid.UUID, kind: str, title: str
) -> None:
    notify(
        db,
        user_id,
        NotificationKind.ACTIVITY_ASSIGNED,
        f"{ACTIVITY_LABELS.get(kind, 'فعالیت')} جدید برای شما: {title}",
        f"assigned:activity:{activity_id}:{user_id}:{uuid.uuid4().hex}",
        body=f"توسط {actor_name}",
        link="/activities",
    )


def record_assigned(
    db: Session,
    user_id: uuid.UUID,
    actor_name: str,
    entity_type: str,
    entity_id: uuid.UUID,
    name: str,
    reason: str | None = None,
) -> None:
    label = RECORD_LABELS.get(entity_type, "پرونده")
    notify(
        db,
        user_id,
        NotificationKind.RECORD_ASSIGNED,
        f"{label} «{name}» به شما سپرده شد",
        f"assigned:{entity_type}:{entity_id}:{user_id}:{uuid.uuid4().hex}",
        body=f"توسط {actor_name}" + (f" — {reason}" if reason else ""),
        link=f"{RECORD_PATHS.get(entity_type, '')}/{entity_id}",
    )
