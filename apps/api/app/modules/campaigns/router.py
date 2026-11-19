"""Campaigns API (spec 4.5). Sales managers and admins; a manager sees the campaigns
they created and reaches only contacts in their own team's scope."""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.modules.audit.service import audit
from app.modules.auth.deps import DbDep, client_ip, require_csrf
from app.modules.campaigns import audience as aud
from app.modules.campaigns import service
from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignStatus,
    RecipientStatus,
    Suppression,
)
from app.modules.crm.access import AccessScope
from app.modules.crm.common import ScopeDep, paginate, require_sales_access
from app.modules.crm.schemas import Page, UserRef
from app.modules.messaging.models import Channel, MessageStatus, OutboundMessage, Purpose
from app.modules.messaging.service import enqueue
from app.modules.notifications.service import fa

router = APIRouter(
    prefix="/campaigns",
    tags=["campaigns"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)
suppressions = APIRouter(
    prefix="/suppressions",
    tags=["campaigns"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)
# Reached from a link inside a message, with no session; the token is the credential.
public = APIRouter(prefix="/public", tags=["public"])

MAX_SMS_TEXT = 1000
MAX_EMAIL_TEXT = 20000


def require_manager(scope: AccessScope) -> None:
    if not (scope.is_admin or scope.is_manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="کمپین با مدیر فروش و ادمین است.")


# -- schemas ------------------------------------------------------------------------------


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    channel: Channel
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(default="", max_length=MAX_EMAIL_TEXT)
    audience: aud.Audience = Field(default_factory=aud.Audience)


class CampaignUpdate(CampaignIn):
    version: int = Field(ge=1)


class Stats(BaseModel):
    total: int = 0
    pending: int = 0
    skipped: int = 0
    in_queue: int = 0  # queued or being sent
    accepted: int = 0  # taken by the provider; not proof of delivery
    delivered: int = 0
    failed: int = 0
    unknown: int = 0
    cost: int = 0


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    channel: Channel
    subject: str | None
    body: str
    audience: dict[str, Any]
    status: CampaignStatus
    scheduled_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    waiting_reason: str | None
    created_by: UserRef
    created_at: datetime
    updated_at: datetime
    version: int
    stats: Stats = Field(default_factory=Stats)


class Preview(BaseModel):
    contacts: int
    eligible: int
    excluded: dict[str, int]
    parts: int | None  # SMS parts per message (with the unsubscribe line)
    unit_cost: int
    estimated_cost: int
    sample_name: str | None
    sample_subject: str | None
    sample_text: str | None
    daily_limit: int
    window: str
    budget_left: int | None


class StartIn(BaseModel):
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def _aware(self) -> "StartIn":
        if self.scheduled_at is not None and self.scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at needs a time zone")
        return self


class RecipientOut(BaseModel):
    id: uuid.UUID
    contact_type: str
    contact_id: uuid.UUID
    name: str
    address: str | None
    status: str  # pending | skipped | in_queue | accepted | delivered | failed | unknown
    reason: str | None
    sent_at: datetime | None
    delivered_at: datetime | None


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    window_start: time
    window_end: time
    sms_daily_limit: int
    email_daily_limit: int
    sms_unit_price: int
    email_unit_price: int
    monthly_budget: int | None
    user_daily_limit: int
    spent_30_days: int = 0


class PolicyIn(BaseModel):
    window_start: time
    window_end: time
    sms_daily_limit: int = Field(ge=0, le=1_000_000)
    email_daily_limit: int = Field(ge=0, le=1_000_000)
    sms_unit_price: int = Field(ge=0, le=10**9)
    email_unit_price: int = Field(ge=0, le=10**9)
    monthly_budget: int | None = Field(default=None, ge=0, le=10**15)
    user_daily_limit: int = Field(default=20, ge=0, le=10_000)

    @model_validator(mode="after")
    def _order(self) -> "PolicyIn":
        if self.window_start >= self.window_end:
            raise ValueError("window_start must be before window_end")
        return self


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: Channel
    address: str
    reason: str
    note: str | None
    created_at: datetime


class SuppressionIn(BaseModel):
    channel: Channel
    address: str = Field(min_length=3, max_length=254)
    note: str | None = Field(default=None, max_length=300)


# -- helpers ------------------------------------------------------------------------------------


def _load(
    db: Session, scope: AccessScope, campaign_id: uuid.UUID, *, lock: bool = False
) -> Campaign:
    require_manager(scope)
    query = select(Campaign).where(Campaign.id == campaign_id)
    if lock:
        query = query.with_for_update(of=Campaign)
    campaign = db.scalar(query)
    if campaign is None or (not scope.is_admin and campaign.created_by_id != scope.user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="کمپین پیدا نشد.")
    return campaign


_DISPLAY = case(
    (CampaignRecipient.status == RecipientStatus.PENDING, "pending"),
    (CampaignRecipient.status == RecipientStatus.SKIPPED, "skipped"),
    (OutboundMessage.status.in_([MessageStatus.QUEUED, MessageStatus.SENDING]), "in_queue"),
    (OutboundMessage.status == MessageStatus.ACCEPTED, "accepted"),
    (OutboundMessage.status == MessageStatus.DELIVERED, "delivered"),
    (OutboundMessage.status == MessageStatus.UNKNOWN, "unknown"),
    else_="failed",
)


def _stats(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, Stats]:
    result = {i: Stats() for i in ids}
    if not ids:
        return result
    rows = db.execute(
        select(
            CampaignRecipient.campaign_id,
            _DISPLAY,
            func.count(),
            func.coalesce(func.sum(CampaignRecipient.cost), 0),
        )
        .outerjoin(OutboundMessage, OutboundMessage.id == CampaignRecipient.message_id)
        .where(CampaignRecipient.campaign_id.in_(ids))
        .group_by(CampaignRecipient.campaign_id, _DISPLAY)
    )
    for campaign_id, key, count, cost in rows:
        stats = result[campaign_id]
        setattr(stats, key, int(count))
        stats.total += int(count)
        stats.cost += int(cost)
    return result


def _out(db: Session, campaign: Campaign) -> CampaignOut:
    out = CampaignOut.model_validate(campaign)
    out.stats = _stats(db, [campaign.id])[campaign.id]
    return out


def _check_content(campaign: Campaign) -> None:
    body = campaign.body.strip()
    if len(body) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="متن پیام لازم است.")
    if campaign.channel is Channel.SMS and len(body) > MAX_SMS_TEXT:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"متن پیامک حداکثر {fa(MAX_SMS_TEXT)} نویسه است.",
        )
    if campaign.channel is Channel.EMAIL and not (campaign.subject or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="موضوع ایمیل لازم است.")


def _preview(db: Session, scope: AccessScope, campaign: Campaign) -> Preview:
    rules = service.policy(db)
    contacts = aud.resolve(db, scope, aud.Audience.model_validate(campaign.audience))
    evaluated = aud.evaluate(db, contacts, campaign.channel)
    excluded: dict[str, int] = {}
    for item in evaluated:
        if item.reason:
            excluded[item.reason] = excluded.get(item.reason, 0) + 1
    eligible = [e for e in evaluated if e.reason is None]
    sample = eligible[0].contact if eligible else (contacts[0] if contacts else None)
    # A representative token: the real one is per recipient but always this long.
    text = aud.full_text(campaign.channel, campaign.body, sample.name if sample else "", "0" * 48)
    unit = aud.unit_cost(campaign.channel, text, rules)
    limit = rules.sms_daily_limit if campaign.channel is Channel.SMS else rules.email_daily_limit
    now = datetime.now(UTC)
    return Preview(
        contacts=len(contacts),
        eligible=len(eligible),
        excluded=excluded,
        parts=aud.sms_parts(text) if campaign.channel is Channel.SMS else None,
        unit_cost=unit,
        estimated_cost=unit * len(eligible),
        sample_name=sample.name if sample else None,
        sample_subject=aud.render(campaign.subject or "", sample.name) if sample else None,
        sample_text=text if sample else None,
        daily_limit=limit,
        window=f"{service.hhmm(rules.window_start)} تا {service.hhmm(rules.window_end)}",
        budget_left=(
            max(rules.monthly_budget - service.spent_30_days(db, now), 0)
            if rules.monthly_budget is not None
            else None
        ),
    )


# -- campaigns ---------------------------------------------------------------------------------


@router.get("")
def list_campaigns(
    db: DbDep,
    scope: ScopeDep,
    status_: Annotated[CampaignStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[CampaignOut]:
    require_manager(scope)
    query = select(Campaign).order_by(Campaign.updated_at.desc(), Campaign.id)
    if not scope.is_admin:
        query = query.where(Campaign.created_by_id == scope.user.id)
    if status_:
        query = query.where(Campaign.status == status_)
    rows, total = paginate(db, query, page, page_size)
    stats = _stats(db, [c.id for c in rows])
    items = []
    for row in rows:
        out = CampaignOut.model_validate(row)
        out.stats = stats[row.id]
        items.append(out)
    return Page[CampaignOut](items=items, total=total, page=page, page_size=page_size)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_campaign(body: CampaignIn, db: DbDep, scope: ScopeDep) -> CampaignOut:
    require_manager(scope)
    campaign = Campaign(
        name=body.name.strip(),
        channel=body.channel,
        subject=body.subject,
        body=body.body,
        audience=body.audience.model_dump(mode="json"),
        created_by_id=scope.user.id,
        created_by=scope.user,
    )
    db.add(campaign)
    db.commit()
    return _out(db, campaign)


@router.get("/policy")
def get_policy(db: DbDep, scope: ScopeDep) -> PolicyOut:
    require_manager(scope)
    rules = service.policy(db)
    db.commit()
    out = PolicyOut.model_validate(rules)
    out.spent_30_days = service.spent_30_days(db, datetime.now(UTC))
    return out


@router.put("/policy")
def set_policy(body: PolicyIn, request: Request, db: DbDep, scope: ScopeDep) -> PolicyOut:
    if not scope.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="قواعد ارسال را ادمین تعیین می‌کند.")
    rules = service.policy(db)
    for key, value in body.model_dump().items():
        setattr(rules, key, value)
    rules.updated_by_id = scope.user.id
    audit(
        db,
        "campaign.policy_updated",
        scope.user.id,
        "messaging_policy",
        None,
        body.model_dump(mode="json"),
        client_ip(request),
    )
    db.commit()
    return get_policy(db, scope)


@router.get("/{campaign_id}")
def get_campaign(campaign_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> CampaignOut:
    return _out(db, _load(db, scope, campaign_id))


@router.put("/{campaign_id}")
def update_campaign(
    campaign_id: uuid.UUID, body: CampaignUpdate, db: DbDep, scope: ScopeDep
) -> CampaignOut:
    campaign = _load(db, scope, campaign_id, lock=True)
    if campaign.status is not CampaignStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="فقط کمپین پیش‌نویس قابل ویرایش است.")
    if campaign.version != body.version:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="کمپین هم‌زمان تغییر کرده است. صفحه را به‌روز کنید."
        )
    campaign.name = body.name.strip()
    campaign.channel = body.channel
    campaign.subject = body.subject
    campaign.body = body.body
    campaign.audience = body.audience.model_dump(mode="json")
    campaign.version += 1
    db.commit()
    return _out(db, campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(campaign_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> Response:
    campaign = _load(db, scope, campaign_id, lock=True)
    if campaign.status is not CampaignStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="فقط پیش‌نویس حذف می‌شود.")
    db.delete(campaign)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{campaign_id}/preview")
def preview(campaign_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> Preview:
    """Who would receive it now, who is left out and why, and the estimated cost."""
    campaign = _load(db, scope, campaign_id)
    result = _preview(db, scope, campaign)
    db.commit()
    return result


@router.post("/{campaign_id}/test")
def test_send(campaign_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> dict[str, str]:
    """Sends the message to the user themselves, with their own name."""
    campaign = _load(db, scope, campaign_id)
    _check_content(campaign)
    me = scope.user
    to = me.mobile if campaign.channel is Channel.SMS else me.email
    if not to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="برای ارسال آزمایشی، موبایل یا ایمیل خودتان باید ثبت شده باشد.",
        )
    text = aud.full_text(campaign.channel, campaign.body, me.full_name, "0" * 48)
    enqueue(
        db,
        campaign.channel,
        Purpose.NOTIFICATION,
        to,
        subject=f"[آزمایشی] {aud.render(campaign.subject or '', me.full_name)}",
        body=text,
        user_id=me.id,
    )
    db.commit()
    return {"to": to}


@router.post("/{campaign_id}/start")
def start(
    campaign_id: uuid.UUID, body: StartIn, request: Request, db: DbDep, scope: ScopeDep
) -> CampaignOut:
    """Runs now (the recipient list is fixed now), or at ``scheduled_at``."""
    campaign = _load(db, scope, campaign_id, lock=True)
    if campaign.status is not CampaignStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این کمپین قبلاً اجرا شده است.")
    _check_content(campaign)
    if _preview(db, scope, campaign).eligible == 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="هیچ مخاطبی شرایط دریافت این کمپین را ندارد.",
        )
    now = datetime.now(UTC)
    if body.scheduled_at is not None and body.scheduled_at > now + timedelta(minutes=1):
        if body.scheduled_at > now + timedelta(days=90):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="زمان‌بندی حداکثر ۹۰ روز بعد است."
            )
        campaign.status = CampaignStatus.SCHEDULED
        campaign.scheduled_at = body.scheduled_at
        action = "campaign.scheduled"
    else:
        service.start_now(db, campaign, now)
        action = "campaign.started"
    campaign.version += 1
    audit(
        db,
        action,
        scope.user.id,
        "campaign",
        campaign.id,
        {"scheduled_at": body.scheduled_at.isoformat() if body.scheduled_at else None},
        client_ip(request),
    )
    db.commit()
    return _out(db, campaign)


@router.post("/{campaign_id}/pause")
def pause(campaign_id: uuid.UUID, request: Request, db: DbDep, scope: ScopeDep) -> CampaignOut:
    """Stops sends that have not started. A scheduled campaign goes back to draft."""
    campaign = _load(db, scope, campaign_id, lock=True)
    if campaign.status is CampaignStatus.SCHEDULED:
        campaign.status = CampaignStatus.DRAFT
        campaign.scheduled_at = None
        details: dict[str, Any] = {"unscheduled": True}
    elif campaign.status is CampaignStatus.RUNNING:
        details = {"canceled_messages": service.pause(db, campaign)}
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این کمپین در حال اجرا نیست.")
    campaign.version += 1
    audit(
        db, "campaign.paused", scope.user.id, "campaign", campaign.id, details, client_ip(request)
    )
    db.commit()
    return _out(db, campaign)


@router.post("/{campaign_id}/resume")
def resume(campaign_id: uuid.UUID, request: Request, db: DbDep, scope: ScopeDep) -> CampaignOut:
    campaign = _load(db, scope, campaign_id, lock=True)
    if campaign.status is not CampaignStatus.PAUSED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این کمپین متوقف نیست.")
    campaign.status = CampaignStatus.RUNNING
    campaign.waiting_reason = None
    campaign.version += 1
    audit(db, "campaign.resumed", scope.user.id, "campaign", campaign.id, None, client_ip(request))
    db.commit()
    return _out(db, campaign)


@router.get("/{campaign_id}/recipients")
def recipients(
    campaign_id: uuid.UUID,
    db: DbDep,
    scope: ScopeDep,
    status_: Annotated[
        Literal["pending", "skipped", "in_queue", "accepted", "delivered", "failed", "unknown"]
        | None,
        Query(alias="status"),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[RecipientOut]:
    campaign = _load(db, scope, campaign_id)
    query = (
        select(CampaignRecipient, _DISPLAY.label("display"), OutboundMessage)
        .outerjoin(OutboundMessage, OutboundMessage.id == CampaignRecipient.message_id)
        .where(CampaignRecipient.campaign_id == campaign.id)
        .order_by(CampaignRecipient.created_at, CampaignRecipient.id)
    )
    if status_:
        query = query.where(_DISPLAY.is_not_distinct_from(status_))
    total = int(db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)
    rows = db.execute(query.limit(page_size).offset((page - 1) * page_size)).all()
    items = [
        RecipientOut(
            id=r.id,
            contact_type=r.contact_type,
            contact_id=r.contact_id,
            name=r.name,
            address=r.address,
            status=display,
            reason=r.skip_reason or (m.last_error if m and display == "failed" else None),
            sent_at=m.sent_at if m else None,
            delivered_at=m.delivered_at if m else None,
        )
        for r, display, m in rows
    ]
    return Page[RecipientOut](items=items, total=total, page=page, page_size=page_size)


# -- do-not-send list ------------------------------------------------------------------------------


def _normalize(channel: Channel, address: str) -> str:
    from app.core.normalize import normalize_email, normalize_mobile

    value = normalize_mobile(address) if channel is Channel.SMS else normalize_email(address)
    if value is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="نشانی معتبر نیست.")
    return value


@suppressions.get("")
def list_suppressions(
    db: DbDep,
    scope: ScopeDep,
    channel: Channel | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[SuppressionOut]:
    require_manager(scope)
    query = select(Suppression).order_by(Suppression.created_at.desc(), Suppression.id)
    if channel:
        query = query.where(Suppression.channel == channel)
    if q:
        query = query.where(or_(Suppression.address.contains(q.strip().lower())))
    rows, total = paginate(db, query, page, page_size)
    return Page[SuppressionOut](
        items=[SuppressionOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@suppressions.post("", status_code=status.HTTP_201_CREATED)
def add_suppression(
    body: SuppressionIn, request: Request, db: DbDep, scope: ScopeDep
) -> SuppressionOut:
    require_manager(scope)
    address = _normalize(body.channel, body.address)
    if db.scalar(
        select(Suppression).where(
            Suppression.channel == body.channel, Suppression.address == address
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این نشانی در فهرست هست.")
    row = Suppression(
        channel=body.channel,
        address=address,
        reason="manual",
        note=body.note,
        created_by_id=scope.user.id,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        "suppression.added",
        scope.user.id,
        "suppression",
        row.id,
        {"channel": body.channel.value},
        client_ip(request),
    )
    db.commit()
    return SuppressionOut.model_validate(row)


@suppressions.delete("/{suppression_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_suppression(
    suppression_id: uuid.UUID, request: Request, db: DbDep, scope: ScopeDep
) -> Response:
    """Only an admin can take an address off the list (e.g. after renewed consent)."""
    if not scope.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="فقط ادمین می‌تواند حذف کند.")
    row = db.get(Suppression, suppression_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="پیدا نشد.")
    audit(
        db,
        "suppression.removed",
        scope.user.id,
        "suppression",
        row.id,
        {"channel": row.channel.value, "reason": row.reason},
        client_ip(request),
    )
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -- unsubscribe link -------------------------------------------------------------


class UnsubscribeOut(BaseModel):
    channel: Channel
    address: str  # masked
    unsubscribed: bool


def _mask(channel: Channel, address: str) -> str:
    if channel is Channel.SMS:
        return address[:6] + "•••" + address[-3:]
    name, _, domain = address.partition("@")
    return (name[:2] + "•••@" + domain) if domain else "•••"


def _from_token(db: Session, token: str) -> tuple[Channel, str]:
    recipient_id = aud.read_token(token)
    found = service.recipient_address(db, recipient_id) if recipient_id else None
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="این پیوند معتبر نیست.")
    return found


@public.get("/unsubscribe/{token}")
def unsubscribe_status(token: str, db: DbDep) -> UnsubscribeOut:
    """What the link is for; nothing changes until the person confirms (link scanners
    in mail systems open links on their own)."""
    channel, address = _from_token(db, token)
    done = db.scalar(
        select(Suppression.id).where(Suppression.channel == channel, Suppression.address == address)
    )
    return UnsubscribeOut(channel=channel, address=_mask(channel, address), unsubscribed=bool(done))


@public.post("/unsubscribe/{token}")
def unsubscribe(token: str, db: DbDep) -> UnsubscribeOut:
    channel, address = _from_token(db, token)
    service.unsubscribe(db, channel, address)
    audit(db, "suppression.unsubscribed", None, "suppression", None, {"channel": channel.value})
    db.commit()
    return UnsubscribeOut(channel=channel, address=_mask(channel, address), unsubscribed=True)
