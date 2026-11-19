"""Ticket rules shared by the staff and portal APIs (spec 4.9).

Default handling (open question 15, recorded in spec section 0.1): a new ticket goes to
the customer's owner. Staff see tickets assigned to someone in their scope or about a
customer they see in full; managers and admins reassign within their scope. Contacts
of the same company do not see each other's tickets.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.crm.access import AccessScope
from app.modules.crm.models import Customer
from app.modules.identity.models import Team, User
from app.modules.messaging.models import Channel, Purpose
from app.modules.messaging.service import enqueue
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import fa, notify
from app.modules.portal.models import PortalIdentity
from app.modules.tickets.models import Ticket, TicketMessage, TicketStatus

STATUS_LABELS = {
    TicketStatus.NEW: "جدید",
    TicketStatus.IN_PROGRESS: "در حال بررسی",
    TicketStatus.WAITING_CUSTOMER: "منتظر پاسخ شما",
    TicketStatus.CLOSED: "بسته‌شده",
}


def visible_filter(scope: AccessScope) -> ColumnElement[bool]:
    ids = scope.owner_ids()
    if ids is None:
        return true()
    return or_(
        Ticket.assignee_id.in_(ids),
        Ticket.customer_id.in_(select(Customer.id).where(Customer.owner_id.in_(ids))),
    )


def can_see(scope: AccessScope, ticket: Ticket) -> bool:
    return (ticket.assignee_id is not None and scope.has_full_access(ticket.assignee_id)) or (
        scope.has_full_access(ticket.customer.owner_id)
    )


def can_manage(scope: AccessScope, ticket: Ticket) -> bool:
    """Reassign: admins, and managers whose team owns the customer or holds the ticket."""
    if scope.is_admin:
        return True
    return scope.is_manager and (
        scope.can_manage(ticket.customer.owner_id)
        or (ticket.assignee_id is not None and scope.can_manage(ticket.assignee_id))
    )


def default_assignee(db: Session, customer: Customer) -> uuid.UUID | None:
    owner = db.get(User, customer.owner_id)
    return owner.id if owner is not None and owner.is_active else None


def staff_to_tell(db: Session, ticket: Ticket) -> uuid.UUID | None:
    """Who hears about customer activity: the assignee, else the owner's team manager."""
    if ticket.assignee_id is not None:
        return ticket.assignee_id
    owner = db.get(User, ticket.customer.owner_id)
    team = db.get(Team, owner.team_id) if owner and owner.team_id else None
    return team.manager_id if team else None


def add_message(
    db: Session,
    ticket: Ticket,
    body: str,
    *,
    user: User | None = None,
    identity: PortalIdentity | None = None,
    internal: bool = False,
) -> TicketMessage:
    message = TicketMessage(
        ticket_id=ticket.id,
        body=body.strip(),
        internal=internal,
        author_user_id=user.id if user else None,
        author_user=user,
        author_identity_id=identity.id if identity else None,
    )
    db.add(message)
    if not internal:
        ticket.last_message_at = datetime.now(UTC)
    ticket.version += 1
    return message


def set_status(ticket: Ticket, status: TicketStatus) -> bool:
    if ticket.status is status:
        return False
    ticket.status = status
    ticket.closed_at = datetime.now(UTC) if status is TicketStatus.CLOSED else None
    return True


def tell_staff(db: Session, ticket: Ticket, title: str, key: str) -> None:
    user_id = staff_to_tell(db, ticket)
    if user_id is not None:
        notify(
            db,
            user_id,
            NotificationKind.TICKET,
            title,
            key,
            body=ticket.subject,
            link=f"/tickets/{ticket.id}",
        )


def tell_customer(db: Session, ticket: Ticket, what: str) -> None:
    """A short operational message to the customer's portal address: never the content,
    only that something changed and where to read it."""
    identity = None
    if ticket.opened_by_identity_id:
        identity = db.get(PortalIdentity, ticket.opened_by_identity_id)
    if identity is None or not identity.is_active:
        identity = db.scalar(
            select(PortalIdentity)
            .where(
                PortalIdentity.customer_id == ticket.customer_id,
                PortalIdentity.is_active.is_(True),
            )
            .order_by(PortalIdentity.created_at)
        )
    if identity is None:
        return
    link = f"{get_settings().public_web_url.rstrip('/')}/portal/tickets/{ticket.id}"
    text = f"{what} درخواست شماره {fa(ticket.number)}.\nمشاهده در پنل مشتری: {link}"
    enqueue(
        db,
        identity.channel,
        Purpose.NOTIFICATION,
        identity.address,
        subject=f"درخواست شماره {fa(ticket.number)}" if identity.channel is Channel.EMAIL else None,
        body=text,
    )
