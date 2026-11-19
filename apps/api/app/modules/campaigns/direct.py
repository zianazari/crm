"""Approved templates and one-off sends from a record (spec section 5: «ارسال تکی قالب
مجاز در پرونده خود با کنترل مصرف»).

* Managers and admins write the templates; anyone with sales access sends only those.
* A person sends from a lead, customer or deal they see in full; a deal's message goes
  to its customer.
* Every send counts against the sender's daily limit and the 30-day budget. Marketing
  templates also need consent, respect the do-not-send list and the sending window,
  count against the organization's daily marketing limit, and carry the unsubscribe
  link. Service templates (about the customer's own business) need only an address.
* ``request_id`` makes a repeated request return the first send instead of sending again.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.audit.service import audit
from app.modules.auth.deps import DbDep, client_ip, require_csrf
from app.modules.campaigns import audience as aud
from app.modules.campaigns import service
from app.modules.campaigns.models import (
    DirectMessage,
    MessageTemplate,
    MessagingPolicy,
    TemplateKind,
)
from app.modules.crm.access import AccessScope
from app.modules.crm.common import NOT_FOUND, ScopeDep, require_sales_access
from app.modules.crm.models import Customer, Lead
from app.modules.crm.schemas import UserRef
from app.modules.messaging.models import Channel, MessageStatus, Purpose
from app.modules.messaging.service import enqueue
from app.modules.notifications.service import fa
from app.modules.sales.models import Deal

templates = APIRouter(
    prefix="/message-templates",
    tags=["direct messages"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)
router = APIRouter(
    prefix="/direct-messages",
    tags=["direct messages"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)

MAX_TEXT = {Channel.SMS: 1000, Channel.EMAIL: 20000}


# -- templates ------------------------------------------------------------------------------


class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    channel: Channel
    kind: TemplateKind
    subject: str | None = Field(default=None, max_length=200)
    body: str = Field(min_length=2, max_length=20000)
    is_active: bool = True

    @model_validator(mode="after")
    def _check(self) -> "TemplateIn":
        if len(self.body) > MAX_TEXT[self.channel]:
            raise ValueError("body too long for the channel")
        if self.channel is Channel.EMAIL and not (self.subject or "").strip():
            raise ValueError("an email template needs a subject")
        return self


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    channel: Channel
    kind: TemplateKind
    subject: str | None
    body: str
    is_active: bool
    updated_at: datetime


def _require_manager(scope: AccessScope) -> None:
    if not (scope.is_admin or scope.is_manager):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="قالب پیام را مدیر فروش یا ادمین تعریف می‌کند."
        )


@templates.get("")
def list_templates(
    db: DbDep,
    scope: ScopeDep,
    channel: Channel | None = None,
    include_inactive: bool = False,
) -> list[TemplateOut]:
    query = select(MessageTemplate).order_by(MessageTemplate.name)
    if channel:
        query = query.where(MessageTemplate.channel == channel)
    if not (include_inactive and (scope.is_admin or scope.is_manager)):
        query = query.where(MessageTemplate.is_active.is_(True))
    return [TemplateOut.model_validate(t) for t in db.scalars(query)]


@templates.post("", status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateIn, request: Request, db: DbDep, scope: ScopeDep) -> TemplateOut:
    _require_manager(scope)
    template = MessageTemplate(**body.model_dump(), created_by_id=scope.user.id)
    template.name = template.name.strip()
    db.add(template)
    db.flush()
    audit(
        db,
        "message_template.created",
        scope.user.id,
        "message_template",
        template.id,
        {"name": template.name, "kind": template.kind.value},
        client_ip(request),
    )
    db.commit()
    return TemplateOut.model_validate(template)


@templates.put("/{template_id}")
def update_template(
    template_id: uuid.UUID, body: TemplateIn, request: Request, db: DbDep, scope: ScopeDep
) -> TemplateOut:
    _require_manager(scope)
    template = db.get(MessageTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="قالب پیدا نشد.")
    for key, value in body.model_dump().items():
        setattr(template, key, value)
    template.name = template.name.strip()
    audit(
        db,
        "message_template.updated",
        scope.user.id,
        "message_template",
        template.id,
        {"name": template.name, "is_active": template.is_active},
        client_ip(request),
    )
    db.commit()
    return TemplateOut.model_validate(template)


# -- checking a send ------------------------------------------------------------------------


class Target(BaseModel):
    template_id: uuid.UUID
    lead_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one(self) -> "Target":
        if sum(x is not None for x in (self.lead_id, self.customer_id, self.deal_id)) != 1:
            raise ValueError("exactly one of lead_id, customer_id, deal_id")
        return self


class SendIn(Target):
    request_id: uuid.UUID


class CheckOut(BaseModel):
    allowed: bool
    reason: str | None
    to: str | None
    contact_name: str
    subject: str | None
    text: str
    parts: int | None
    cost: int
    sent_today: int
    daily_limit: int


@dataclass
class Prepared:
    template: MessageTemplate
    contact: Lead | Customer
    deal: Deal | None
    result: CheckOut


def _contact(
    db: Session, scope: AccessScope, target: Target
) -> tuple[Lead | Customer, Deal | None]:
    """The record the person sends from (they must see it in full) and who receives it."""
    if target.deal_id is not None:
        deal = db.get(Deal, target.deal_id)
        if deal is None or deal.archived_at is not None:
            raise NOT_FOUND
        scope.require_full(deal.owner_id)
        return deal.customer, deal
    record: Lead | Customer | None = (
        db.get(Lead, target.lead_id) if target.lead_id else db.get(Customer, target.customer_id)
    )
    if record is None or record.archived_at is not None:
        raise NOT_FOUND
    scope.require_full(record.owner_id)
    return record, None


def _render(text: str, contact: Lead | Customer, deal: Deal | None, sender: str) -> str:
    return (
        text.replace("{name}", contact.full_name)
        .replace("{deal}", deal.title if deal else "")
        .replace("{owner}", sender)
        .strip()
    )


def sent_today_by(db: Session, user_id: uuid.UUID, now: datetime) -> int:
    midnight = datetime.combine(now.astimezone(service.tz()).date(), time.min, service.tz())
    return int(
        db.scalar(
            select(func.count()).where(
                DirectMessage.sender_id == user_id, DirectMessage.created_at >= midnight
            )
        )
        or 0
    )


def prepare(
    db: Session, scope: AccessScope, target: Target, message_id: uuid.UUID | None = None
) -> Prepared:
    template = db.get(MessageTemplate, target.template_id)
    if template is None or not template.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="قالب پیدا نشد یا غیرفعال است.")
    contact, deal = _contact(db, scope, target)
    rules: MessagingPolicy = service.policy(db)
    now = datetime.now(UTC)
    marketing = template.kind is TemplateKind.MARKETING
    channel = template.channel
    sender = scope.user.full_name

    text = _render(template.body, contact, deal, sender)
    if marketing:
        # The real token is made from the message id when sending; same length here.
        text += aud.footer(channel, aud.unsubscribe_token(message_id or uuid.UUID(int=0)))
    subject = _render(template.subject or "", contact, deal, sender) or None
    cost = aud.unit_cost(channel, text, rules)
    used = sent_today_by(db, scope.user.id, now)

    raw = contact.mobile if channel is Channel.SMS else contact.email
    address = aud.address_of(aud.contact_of(contact), channel) if raw else None
    reason: str | None = None
    if not raw:
        reason = aud.NO_ADDRESS
    elif address is None:
        reason = aud.BAD_ADDRESS
    elif used >= rules.user_daily_limit:
        reason = f"سقف روزانه ارسال تکی شما ({fa(rules.user_daily_limit)} پیام) پر شده است."
    elif marketing:
        consent = contact.sms_consent if channel is Channel.SMS else contact.email_consent
        org_limit = rules.sms_daily_limit if channel is Channel.SMS else rules.email_daily_limit
        if not consent:
            reason = aud.NO_CONSENT
        elif aud.suppressed(db, channel, [address]):
            reason = aud.SUPPRESSED
        elif (why := service.outside_window(rules, now)) is not None:
            reason = why.split(";")[0] + "."
        elif service.sent_today(db, channel, now) >= org_limit:
            reason = "سقف روزانه پیام تبلیغاتی سازمان پر شده است."
    if (
        reason is None
        and rules.monthly_budget is not None
        and service.spent_30_days(db, now) + cost > rules.monthly_budget
    ):
        reason = "سقف مصرف ۳۰ روزه پیام‌ها پر شده است."

    return Prepared(
        template=template,
        contact=contact,
        deal=deal,
        result=CheckOut(
            allowed=reason is None,
            reason=reason,
            to=address,
            contact_name=contact.full_name,
            subject=subject,
            text=text,
            parts=aud.sms_parts(text) if channel is Channel.SMS else None,
            cost=cost,
            sent_today=used,
            daily_limit=rules.user_daily_limit,
        ),
    )


# -- sending ----------------------------------------------------------------------------------


class DirectMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_name: str
    kind: TemplateKind
    channel: Channel
    sender: UserRef
    contact_name: str
    address: str
    text: str
    created_at: datetime
    status: MessageStatus | None = None


def view(row: DirectMessage) -> DirectMessageOut:
    out = DirectMessageOut.model_validate(row)
    out.status = row.message.status if row.message else None
    return out


@router.post("/check")
def check(body: Target, db: DbDep, scope: ScopeDep) -> CheckOut:
    """What would be sent, to whom, at what cost — or why it cannot be."""
    result = prepare(db, scope, body).result
    db.commit()  # the policy row may have been created
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def send(body: SendIn, request: Request, db: DbDep, scope: ScopeDep) -> DirectMessageOut:
    earlier = db.scalar(
        select(DirectMessage).where(
            DirectMessage.sender_id == scope.user.id, DirectMessage.request_id == body.request_id
        )
    )
    if earlier is not None:
        return view(earlier)  # the same request again: nothing more is sent

    # One send at a time per person, so the daily limit cannot be raced past.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"direct:{scope.user.id}"))))
    row_id = uuid.uuid4()
    prepared = prepare(db, scope, body, message_id=row_id)
    result = prepared.result
    if not result.allowed or result.to is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=result.reason)
    template = prepared.template
    marketing = template.kind is TemplateKind.MARKETING
    message = enqueue(
        db,
        template.channel,
        Purpose.MARKETING if marketing else Purpose.NOTIFICATION,
        result.to,
        subject=result.subject,
        body=result.text,
    )
    contact = prepared.contact
    row = DirectMessage(
        id=row_id,
        template_id=template.id,
        template_name=template.name,
        kind=template.kind,
        channel=template.channel,
        sender_id=scope.user.id,
        sender=scope.user,
        request_id=body.request_id,
        lead_id=contact.id if isinstance(contact, Lead) else None,
        customer_id=contact.id if isinstance(contact, Customer) else None,
        deal_id=prepared.deal.id if prepared.deal else None,
        contact_name=contact.full_name,
        address=result.to,
        text=result.text,
        message_id=message.id,
        message=message,
        cost=result.cost,
    )
    db.add(row)
    audit(
        db,
        "direct_message.sent",
        scope.user.id,
        "direct_message",
        row.id,
        {"template": template.name, "channel": template.channel.value},
        client_ip(request),
    )
    try:
        db.commit()
    except IntegrityError:
        # The same request committed in parallel: return that one.
        db.rollback()
        existing = db.scalar(
            select(DirectMessage).where(
                DirectMessage.sender_id == scope.user.id,
                DirectMessage.request_id == body.request_id,
            )
        )
        if existing is None:
            raise
        return view(existing)
    return view(row)


@router.get("/usage")
def usage(db: DbDep, scope: ScopeDep) -> dict[str, int]:
    rules = service.policy(db)
    db.commit()
    return {
        "sent_today": sent_today_by(db, scope.user.id, datetime.now(UTC)),
        "daily_limit": rules.user_daily_limit,
    }


@router.get("")
def list_sent(
    db: DbDep,
    scope: ScopeDep,
    mine: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[DirectMessageOut]:
    query = select(DirectMessage).order_by(DirectMessage.created_at.desc()).limit(limit)
    if mine or not scope.is_admin:
        query = query.where(DirectMessage.sender_id == scope.user.id)
    return [view(r) for r in db.scalars(query)]
