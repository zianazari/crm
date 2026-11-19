"""Staff turn portal access on and off for a customer (spec 4.9, section 5).

Access uses an address already on the customer's record (its mobile or email), so the
customer proves it by receiving the code. Whoever sees the customer in full may do
this; turning it off ends the customer's portal sessions immediately.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.normalize import normalize_email, normalize_mobile
from app.modules.audit.service import audit
from app.modules.auth.deps import DbDep, client_ip, require_csrf
from app.modules.crm.common import NOT_FOUND, ScopeDep, require_sales_access
from app.modules.crm.models import Customer
from app.modules.messaging.models import Channel
from app.modules.portal.auth import revoke_sessions
from app.modules.portal.models import PortalIdentity

router = APIRouter(
    prefix="/portal-access",
    tags=["portal"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)


class AccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: Channel
    address: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class AccessIn(BaseModel):
    customer_id: uuid.UUID
    channel: Channel


def _customer(db: DbDep, scope: ScopeDep, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.archived_at is not None:
        raise NOT_FOUND
    scope.require_full(customer.owner_id)
    return customer


@router.get("")
def list_access(customer_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> list[AccessOut]:
    customer = _customer(db, scope, customer_id)
    rows = db.scalars(
        select(PortalIdentity)
        .where(PortalIdentity.customer_id == customer.id)
        .order_by(PortalIdentity.created_at)
    )
    return [AccessOut.model_validate(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def enable(body: AccessIn, request: Request, db: DbDep, scope: ScopeDep) -> AccessOut:
    customer = _customer(db, scope, body.customer_id)
    raw = customer.mobile if body.channel is Channel.SMS else customer.email
    address = (
        (normalize_mobile(raw) if body.channel is Channel.SMS else normalize_email(raw))
        if raw
        else None
    )
    if address is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ابتدا موبایل یا ایمیل معتبر مشتری را در پرونده ثبت کنید.",
        )
    existing = db.scalar(
        select(PortalIdentity).where(
            PortalIdentity.channel == body.channel, PortalIdentity.address == address
        )
    )
    if existing is not None and existing.customer_id != customer.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "این نشانی برای پنل مشتری دیگری فعال شده است؛ هر نشانی فقط به یک مشتری راه دارد."
            ),
        )
    if existing is None:
        existing = PortalIdentity(
            customer_id=customer.id,
            channel=body.channel,
            address=address,
            created_by_id=scope.user.id,
        )
        db.add(existing)
    existing.is_active = True
    existing.disabled_at = None
    db.flush()
    audit(
        db,
        "portal.access_enabled",
        scope.user.id,
        "customer",
        customer.id,
        {"channel": body.channel.value},
        client_ip(request),
    )
    db.commit()
    return AccessOut.model_validate(existing)


@router.post("/{identity_id}/disable")
def disable(identity_id: uuid.UUID, request: Request, db: DbDep, scope: ScopeDep) -> AccessOut:
    identity = db.get(PortalIdentity, identity_id)
    if identity is None:
        raise NOT_FOUND
    _customer(db, scope, identity.customer_id)
    identity.is_active = False
    identity.disabled_at = datetime.now(UTC)
    revoke_sessions(db, identity.id)
    audit(
        db,
        "portal.access_disabled",
        scope.user.id,
        "customer",
        identity.customer_id,
        {"channel": identity.channel.value},
        client_ip(request),
    )
    db.commit()
    return AccessOut.model_validate(identity)
