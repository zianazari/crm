"""Tickets in the customer portal (spec 4.9; criterion 17).

The customer sees only their own tickets and only public messages. Every lookup is by
ticket id *and* the signed-in customer, so changing an id in the address shows nothing
of anyone else. Opening and replying are rate limited per identity.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy import select

from app.core.redis import get_redis
from app.modules.auth.deps import DbDep
from app.modules.crm.common import paginate
from app.modules.crm.schemas import Page
from app.modules.notifications.service import fa
from app.modules.portal.auth import PortalUserDep, require_portal_csrf
from app.modules.tickets import service
from app.modules.tickets.models import Ticket, TicketMessage, TicketStatus

router = APIRouter(
    prefix="/portal/tickets", tags=["portal"], dependencies=[Depends(require_portal_csrf)]
)

TICKETS_PER_DAY = 10
MESSAGES_PER_HOUR = 30


class PortalTicket(BaseModel):
    id: uuid.UUID
    number: int
    subject: str
    status: TicketStatus
    status_label: str
    created_at: datetime
    last_message_at: datetime


class PortalMessage(BaseModel):
    id: uuid.UUID
    body: str
    from_me: bool
    author: str
    created_at: datetime


class PortalTicketDetail(PortalTicket):
    messages: list[PortalMessage]


class OpenIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=5000)


class ReplyIn(BaseModel):
    body: str = Field(min_length=2, max_length=5000)


def _limit(redis: Redis, key: str, limit: int, seconds: int) -> None:
    pipe = redis.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, seconds, nx=True)
    count, _ = pipe.execute()
    if int(count) > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="تعداد درخواست‌ها زیاد است. کمی بعد دوباره تلاش کنید.",
            headers={"Retry-After": str(max(int(redis.ttl(key)), 1))},
        )


def _summary(ticket: Ticket) -> PortalTicket:
    return PortalTicket(
        id=ticket.id,
        number=ticket.number,
        subject=ticket.subject,
        status=ticket.status,
        status_label=service.STATUS_LABELS[ticket.status],
        created_at=ticket.created_at,
        last_message_at=ticket.last_message_at,
    )


def _detail(db: DbDep, ticket: Ticket) -> PortalTicketDetail:
    rows = db.scalars(
        select(TicketMessage)
        .where(TicketMessage.ticket_id == ticket.id, TicketMessage.internal.is_(False))
        .order_by(TicketMessage.created_at, TicketMessage.id)
    )
    return PortalTicketDetail(
        **_summary(ticket).model_dump(),
        messages=[
            PortalMessage(
                id=m.id,
                body=m.body,
                from_me=m.author_identity_id is not None,
                # Staff are shown by first name only on the customer side.
                author="شما"
                if m.author_identity_id is not None
                else (m.author_user.full_name.split()[0] if m.author_user else "پشتیبانی"),
                created_at=m.created_at,
            )
            for m in rows
        ],
    )


def _own(db: DbDep, user: PortalUserDep, ticket_id: uuid.UUID, lock: bool = False) -> Ticket:
    query = select(Ticket).where(Ticket.id == ticket_id, Ticket.customer_id == user.customer_id)
    if lock:
        query = query.with_for_update(of=Ticket)
    ticket = db.scalar(query)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="درخواست پیدا نشد.")
    return ticket


@router.get("")
def my_tickets(
    db: DbDep,
    user: PortalUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[PortalTicket]:
    query = (
        select(Ticket)
        .where(Ticket.customer_id == user.customer_id)
        .order_by(Ticket.last_message_at.desc(), Ticket.id)
    )
    rows, total = paginate(db, query, page, page_size)
    return Page[PortalTicket](
        items=[_summary(t) for t in rows], total=total, page=page, page_size=page_size
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def open_ticket(
    body: OpenIn, db: DbDep, user: PortalUserDep, redis: Annotated[Redis, Depends(get_redis)]
) -> PortalTicketDetail:
    _limit(redis, f"portal:rl:tickets:{user.identity.id}", TICKETS_PER_DAY, 86400)
    customer = user.identity.customer
    ticket = Ticket(
        customer_id=customer.id,
        customer=customer,
        subject=body.subject.strip(),
        assignee_id=service.default_assignee(db, customer),
        opened_by_identity_id=user.identity.id,
    )
    db.add(ticket)
    db.flush()
    service.add_message(db, ticket, body.body, identity=user.identity)
    service.tell_staff(
        db,
        ticket,
        f"تیکت تازه از {customer.full_name} (شماره {fa(ticket.number)})",
        f"ticket-new:{ticket.id}",
    )
    db.commit()
    db.refresh(ticket)
    return _detail(db, ticket)


@router.get("/{ticket_id}")
def my_ticket(ticket_id: uuid.UUID, db: DbDep, user: PortalUserDep) -> PortalTicketDetail:
    return _detail(db, _own(db, user, ticket_id))


@router.post("/{ticket_id}/messages")
def add_reply(
    ticket_id: uuid.UUID,
    body: ReplyIn,
    db: DbDep,
    user: PortalUserDep,
    redis: Annotated[Redis, Depends(get_redis)],
) -> PortalTicketDetail:
    _limit(redis, f"portal:rl:messages:{user.identity.id}", MESSAGES_PER_HOUR, 3600)
    ticket = _own(db, user, ticket_id, lock=True)
    service.add_message(db, ticket, body.body, identity=user.identity)
    # The customer answered (or reopened a closed one): it is back with the staff.
    if ticket.status is not TicketStatus.NEW:
        service.set_status(ticket, TicketStatus.IN_PROGRESS)
    service.tell_staff(
        db,
        ticket,
        f"پاسخ تازه از {ticket.customer.full_name} در تیکت شماره {fa(ticket.number)}",
        f"ticket-reply:{ticket.id}:{ticket.version}",
    )
    db.commit()
    return _detail(db, ticket)
