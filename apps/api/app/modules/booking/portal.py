"""The customer's own bookings in the portal (spec 4.9 «زمان‌های رزروشده خودش», 4.10).

Every lookup is by booking id *and* the signed-in customer, so another id shows nothing.
Moving and canceling follow the same deadline and atomic rules as the booking link.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.auth.deps import DbDep
from app.modules.booking import availability, service
from app.modules.booking.models import Booking, BookingStatus
from app.modules.booking.schemas import CancelIn, Slots, StartIn
from app.modules.booking.views import slots_out
from app.modules.portal.auth import PortalUser, PortalUserDep, require_portal_csrf

router = APIRouter(
    prefix="/portal/bookings", tags=["portal"], dependencies=[Depends(require_portal_csrf)]
)


class PortalBooking(BaseModel):
    id: uuid.UUID
    status: BookingStatus
    meeting_title: str
    meeting_description: str | None
    staff_name: str
    start_at: datetime
    end_at: datetime
    can_change: bool
    change_until: datetime
    canceled_at: datetime | None


def _out(db: Session, booking: Booking) -> PortalBooking:
    return PortalBooking(
        id=booking.id,
        status=booking.status,
        meeting_title=booking.meeting_type.title,
        meeting_description=booking.meeting_type.description,
        staff_name=booking.user.full_name,
        start_at=booking.start_at,
        end_at=booking.end_at,
        can_change=service.can_change(db, booking) and booking.link.revoked_at is None,
        change_until=service.change_deadline(db, booking),
        canceled_at=booking.canceled_at,
    )


def _mine(db: Session, user: PortalUser, booking_id: uuid.UUID, *, lock: bool = False) -> Booking:
    query = select(Booking).where(Booking.id == booking_id, Booking.customer_id == user.customer_id)
    if lock:
        query = query.with_for_update(of=Booking)
    booking = db.scalar(query)
    if booking is None or booking.status is BookingStatus.RESCHEDULED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="رزرو پیدا نشد.")
    return booking


def _changeable(db: Session, user: PortalUser, booking_id: uuid.UUID) -> Booking:
    booking = _mine(db, user, booking_id, lock=True)
    if booking.status is not BookingStatus.CONFIRMED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این رزرو لغو شده است.")
    if booking.link.revoked_at is not None or not service.can_change(db, booking):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="مهلت لغو یا تغییر این جلسه گذشته است. با کارشناس خود تماس بگیرید.",
        )
    return booking


def _portal_url() -> str:
    return f"{get_settings().public_web_url.rstrip('/')}/portal"


@router.get("")
def my_bookings(db: DbDep, user: PortalUserDep) -> list[PortalBooking]:
    """Upcoming confirmed meetings first, then the recent past and canceled ones."""
    rows = list(
        db.scalars(
            select(Booking)
            .where(
                Booking.customer_id == user.customer_id,
                Booking.status != BookingStatus.RESCHEDULED,
            )
            .order_by(Booking.start_at.desc())
            .limit(50)
        )
    )
    now = datetime.now(UTC)
    upcoming = sorted(
        (b for b in rows if b.status is BookingStatus.CONFIRMED and b.end_at > now),
        key=lambda b: b.start_at,
    )
    rest = [b for b in rows if b not in upcoming]
    result = [_out(db, b) for b in upcoming + rest]
    db.commit()
    return result


@router.get("/{booking_id}/slots")
def booking_slots(booking_id: uuid.UUID, db: DbDep, user: PortalUserDep) -> Slots:
    booking = _changeable(db, user, booking_id)
    calendar = availability.load(db, booking.user_id, ignore_booking=booking)
    result = slots_out(calendar, booking.meeting_type)
    db.commit()
    return result


@router.post("/{booking_id}/reschedule")
def move(booking_id: uuid.UUID, body: StartIn, db: DbDep, user: PortalUserDep) -> PortalBooking:
    booking = _changeable(db, user, booking_id)
    try:
        replacement = service.reschedule(db, booking, body.start_at, _portal_url())
    except service.SlotTakenError:
        db.rollback()
        raise service.raise_taken() from None
    db.commit()
    return _out(db, replacement)


@router.post("/{booking_id}/cancel")
def cancel(booking_id: uuid.UUID, body: CancelIn, db: DbDep, user: PortalUserDep) -> PortalBooking:
    booking = _changeable(db, user, booking_id)
    service.cancel(db, booking, body.reason)
    db.commit()
    db.refresh(booking)
    return _out(db, booking)
