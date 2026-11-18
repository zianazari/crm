import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.modules.auth.deps import DbDep, SettingsDep, require_csrf
from app.modules.crm.common import ScopeDep, paginate
from app.modules.crm.schemas import Page
from app.modules.messaging.models import Channel, MessageStatus, OutboundMessage, Purpose
from app.modules.messaging.service import (
    InvalidSignatureError,
    apply_delivery_report,
    parse_json,
    verify_signature,
)

webhooks = APIRouter(prefix="/webhooks", tags=["webhooks"])
router = APIRouter(prefix="/messages", tags=["messages"], dependencies=[Depends(require_csrf)])


@webhooks.post("/sms", status_code=status.HTTP_204_NO_CONTENT)
async def sms_delivery_report(request: Request, db: DbDep, settings: SettingsDep) -> Response:
    """Provider delivery reports. Authenticated by HMAC signature, not by session;
    repeated and out-of-order reports are harmless (spec 7)."""
    body = await request.body()
    try:
        verify_signature(
            settings.sms_webhook_secret.get_secret_value(),
            body,
            request.headers.get("X-Signature", ""),
        )
        payload = parse_json(body)
    except InvalidSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid signature") from None
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid body") from None
    apply_delivery_report(db, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: Channel
    purpose: Purpose
    recipient: str
    subject: str | None
    status: MessageStatus
    attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None


@router.get("")
def list_messages(
    db: DbDep,
    scope: ScopeDep,
    status_: Annotated[MessageStatus | None, Query(alias="status")] = None,
    channel: Channel | None = None,
    purpose: Purpose | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[MessageOut]:
    """Delivery log for admins (spec 10: observability of sending)."""
    if not scope.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="فقط ادمین گزارش ارسال را می‌بیند.")
    query = select(OutboundMessage).order_by(OutboundMessage.created_at.desc(), OutboundMessage.id)
    if status_:
        query = query.where(OutboundMessage.status == status_)
    if channel:
        query = query.where(OutboundMessage.channel == channel)
    if purpose:
        query = query.where(OutboundMessage.purpose == purpose)
    rows, total = paginate(db, query, page, page_size)
    return Page[MessageOut](
        items=[MessageOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
