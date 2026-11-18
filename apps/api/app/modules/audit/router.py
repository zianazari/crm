import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.modules.audit.models import AuditLog
from app.modules.auth.deps import DbDep, require_csrf
from app.modules.crm.common import ScopeDep, day_bounds, paginate
from app.modules.crm.schemas import Page, UserRef

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_csrf)])


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    actor: UserRef | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    details: dict[str, Any] | None
    ip_address: str | None
    at: datetime


@router.get("")
def list_audit(
    db: DbDep,
    scope: ScopeDep,
    action: Annotated[str | None, Query(max_length=50)] = None,
    actor_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[AuditOut]:
    """Admins only: the log itself is sensitive (spec 10: access to logs is restricted)."""
    if not scope.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="فقط ادمین سوابق ممیزی را می‌بیند.")
    query = select(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id)
    if action:
        query = query.where(AuditLog.action.startswith(action, autoescape=True))
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    start, end = day_bounds(date_from, date_to)
    if start:
        query = query.where(AuditLog.at >= start)
    if end:
        query = query.where(AuditLog.at < end)
    rows, total = paginate(db, query, page, page_size)
    return Page[AuditOut](
        items=[AuditOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
