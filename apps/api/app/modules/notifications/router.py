import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update

from app.modules.auth.deps import CurrentUserDep, DbDep, require_csrf
from app.modules.notifications.models import Notification, NotificationKind

router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_csrf)]
)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: NotificationKind
    title: str
    body: str | None
    link: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    unread: int
    has_more: bool


@router.get("")
def list_notifications(
    db: DbDep,
    current: CurrentUserDep,
    unread_only: bool = False,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> NotificationPage:
    """The user's own notifications, newest first; page with ``before``."""
    query = (
        select(Notification)
        .where(Notification.user_id == current.user.id)
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(limit + 1)
    )
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    if before is not None:
        query = query.where(Notification.created_at < before)
    rows = list(db.scalars(query))
    return NotificationPage(
        items=[NotificationOut.model_validate(n) for n in rows[:limit]],
        unread=_unread(db, current.user.id),
        has_more=len(rows) > limit,
    )


def _unread(db: DbDep, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
        or 0
    )


@router.get("/unread-count")
def unread_count(db: DbDep, current: CurrentUserDep) -> dict[str, int]:
    return {"unread": _unread(db, current.user.id)}


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(notification_id: uuid.UUID, db: DbDep, current: CurrentUserDep) -> None:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != current.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="اعلان پیدا نشد.")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(db: DbDep, current: CurrentUserDep) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == current.user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
