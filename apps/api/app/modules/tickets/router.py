"""Tickets in the staff panel (spec 4.9): list, open on a customer's behalf, reply to the
customer or add an internal note, change status, reassign."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, or_, select

from app.modules.audit.service import audit
from app.modules.auth.deps import DbDep, client_ip, require_csrf
from app.modules.crm.common import NOT_FOUND, ScopeDep, paginate, require_sales_access
from app.modules.crm.models import Customer
from app.modules.crm.schemas import Page, UserRef
from app.modules.identity.models import User
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import fa, notify
from app.modules.tickets import service
from app.modules.tickets.models import Ticket, TicketMessage, TicketStatus

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)

Body = Annotated[str, Field(min_length=2, max_length=5000)]


class CustomerRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    subject: str
    status: TicketStatus
    customer: CustomerRef
    assignee: UserRef | None
    opened_by_user: UserRef | None
    opened_by_customer: bool = False
    created_at: datetime
    last_message_at: datetime
    closed_at: datetime | None
    version: int
    can_manage: bool = False


class MessageOut(BaseModel):
    id: uuid.UUID
    body: str
    internal: bool
    author: str
    from_customer: bool
    created_at: datetime


class TicketDetail(TicketOut):
    messages: list[MessageOut]


class TicketCreate(BaseModel):
    customer_id: uuid.UUID
    subject: str = Field(min_length=3, max_length=200)
    body: Body


class MessageIn(BaseModel):
    body: Body
    internal: bool = False
    # Optional status change with the reply; a public reply defaults to «منتظر پاسخ».
    status: TicketStatus | None = None


class StatusIn(BaseModel):
    status: TicketStatus


class AssignIn(BaseModel):
    user_id: uuid.UUID


def _out(scope: ScopeDep, ticket: Ticket) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    out.opened_by_customer = ticket.opened_by_identity_id is not None
    out.can_manage = service.can_manage(scope, ticket)
    return out


def _messages(db: DbDep, ticket: Ticket) -> list[MessageOut]:
    rows = db.scalars(
        select(TicketMessage)
        .where(TicketMessage.ticket_id == ticket.id)
        .order_by(TicketMessage.created_at, TicketMessage.id)
    )
    return [
        MessageOut(
            id=m.id,
            body=m.body,
            internal=m.internal,
            author=m.author_user.full_name if m.author_user else ticket.customer.full_name,
            from_customer=m.author_identity_id is not None,
            created_at=m.created_at,
        )
        for m in rows
    ]


def _detail(db: DbDep, scope: ScopeDep, ticket: Ticket) -> TicketDetail:
    return TicketDetail(**_out(scope, ticket).model_dump(), messages=_messages(db, ticket))


def _load(db: DbDep, scope: ScopeDep, ticket_id: uuid.UUID, lock: bool = False) -> Ticket:
    query = select(Ticket).where(Ticket.id == ticket_id)
    if lock:
        query = query.with_for_update(of=Ticket)
    ticket = db.scalar(query)
    if ticket is None or not service.can_see(scope, ticket):
        raise NOT_FOUND
    return ticket


@router.get("")
def list_tickets(
    db: DbDep,
    scope: ScopeDep,
    status_: Annotated[
        Literal["open", "new", "in_progress", "waiting_customer", "closed", "all"],
        Query(alias="status"),
    ] = "open",
    mine: bool = False,
    customer_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[TicketOut]:
    query = (
        select(Ticket)
        .join(Customer, Customer.id == Ticket.customer_id)
        .where(service.visible_filter(scope))
        .order_by(Ticket.last_message_at.desc(), Ticket.id)
    )
    if status_ == "open":
        query = query.where(Ticket.status != TicketStatus.CLOSED)
    elif status_ != "all":
        query = query.where(Ticket.status == TicketStatus(status_))
    if mine:
        query = query.where(Ticket.assignee_id == scope.user.id)
    if customer_id:
        query = query.where(Ticket.customer_id == customer_id)
    if q:
        term = q.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
        conditions: list[ColumnElement[bool]] = [
            Ticket.subject.ilike(f"%{term}%"),
            Customer.full_name.ilike(f"%{term}%"),
        ]
        if term.isdigit():
            conditions.append(Ticket.number == int(term))
        query = query.where(or_(*conditions))
    rows, total = paginate(db, query, page, page_size)
    return Page[TicketOut](
        items=[_out(scope, t) for t in rows], total=total, page=page, page_size=page_size
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_ticket(body: TicketCreate, request: Request, db: DbDep, scope: ScopeDep) -> TicketDetail:
    """Opened by staff on the customer's behalf (e.g. after a call)."""
    customer = db.get(Customer, body.customer_id)
    if customer is None or customer.archived_at is not None:
        raise NOT_FOUND
    scope.require_full(customer.owner_id)
    ticket = Ticket(
        customer_id=customer.id,
        customer=customer,
        subject=body.subject.strip(),
        status=TicketStatus.IN_PROGRESS,
        assignee_id=service.default_assignee(db, customer),
        opened_by_user_id=scope.user.id,
    )
    db.add(ticket)
    db.flush()
    service.add_message(db, ticket, body.body, user=scope.user)
    audit(db, "ticket.created", scope.user.id, "ticket", ticket.id, None, client_ip(request))
    db.commit()
    db.refresh(ticket)
    return _detail(db, scope, ticket)


@router.get("/{ticket_id}")
def get_ticket(ticket_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> TicketDetail:
    return _detail(db, scope, _load(db, scope, ticket_id))


@router.post("/{ticket_id}/messages")
def reply(ticket_id: uuid.UUID, body: MessageIn, db: DbDep, scope: ScopeDep) -> TicketDetail:
    ticket = _load(db, scope, ticket_id, lock=True)
    service.add_message(db, ticket, body.body, user=scope.user, internal=body.internal)
    new_status = body.status or (None if body.internal else TicketStatus.WAITING_CUSTOMER)
    changed = service.set_status(ticket, new_status) if new_status else False
    if not body.internal:
        service.tell_customer(db, ticket, "پاسخ تازه‌ای ثبت شد برای")
    elif changed and ticket.status is TicketStatus.CLOSED:
        service.tell_customer(db, ticket, "بسته شد:")
    db.commit()
    return _detail(db, scope, ticket)


@router.post("/{ticket_id}/status")
def change_status(
    ticket_id: uuid.UUID, body: StatusIn, request: Request, db: DbDep, scope: ScopeDep
) -> TicketDetail:
    ticket = _load(db, scope, ticket_id, lock=True)
    if service.set_status(ticket, body.status):
        ticket.version += 1
        if body.status is TicketStatus.CLOSED:
            service.tell_customer(db, ticket, "بسته شد:")
        audit(
            db,
            "ticket.status",
            scope.user.id,
            "ticket",
            ticket.id,
            {"status": body.status.value},
            client_ip(request),
        )
    db.commit()
    return _detail(db, scope, ticket)


@router.post("/{ticket_id}/assign")
def assign(
    ticket_id: uuid.UUID, body: AssignIn, request: Request, db: DbDep, scope: ScopeDep
) -> TicketDetail:
    ticket = _load(db, scope, ticket_id, lock=True)
    if not service.can_manage(scope, ticket):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="واگذاری تیکت با مدیر فروش یا ادمین است."
        )
    user = db.get(User, body.user_id)
    if user is None or not scope.can_assign_to(user):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="این کاربر فعال یا در دامنه شما نیست."
        )
    if ticket.assignee_id != user.id:
        ticket.assignee_id, ticket.assignee = user.id, user
        ticket.version += 1
        if user.id != scope.user.id:
            notify(
                db,
                user.id,
                NotificationKind.TICKET,
                f"تیکت شماره {fa(ticket.number)} به شما واگذار شد",
                f"ticket-assigned:{ticket.id}:{user.id}:{ticket.version}",
                body=ticket.subject,
                link=f"/tickets/{ticket.id}",
            )
        audit(
            db,
            "ticket.assigned",
            scope.user.id,
            "ticket",
            ticket.id,
            {"to": str(user.id)},
            client_ip(request),
        )
    db.commit()
    return _detail(db, scope, ticket)
