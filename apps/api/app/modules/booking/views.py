"""Output shapes shared by the staff, public and portal booking APIs."""

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.modules.booking import availability, service
from app.modules.booking.models import Booking, BookingLink, MeetingType
from app.modules.booking.schemas import (
    BookingOut,
    CustomerRef,
    Day,
    LinkOut,
    MeetingTypeOut,
    Slots,
)
from app.modules.crm.schemas import UserRef


def booking_out(booking: Booking) -> BookingOut:
    return BookingOut(
        id=booking.id,
        status=booking.status,
        start_at=booking.start_at,
        end_at=booking.end_at,
        meeting_title=booking.meeting_type.title,
        user=UserRef.model_validate(booking.user),
        customer=CustomerRef.model_validate(booking.customer),
        activity_id=booking.activity_id,
        deal_id=booking.deal_id,
        contact_channel=booking.contact_channel,
        created_at=booking.created_at,
        canceled_at=booking.canceled_at,
        cancel_reason=booking.cancel_reason,
        canceled_by=UserRef.model_validate(booking.canceled_by) if booking.canceled_by else None,
        rescheduled_to_id=booking.rescheduled_to_id,
    )


def link_out(db: Session, link: BookingLink) -> LinkOut:
    active = service.active_booking(db, link)
    return LinkOut(
        id=link.id,
        user=UserRef.model_validate(link.user),
        customer=CustomerRef.model_validate(link.customer),
        meeting_type=MeetingTypeOut.model_validate(link.meeting_type),
        deal_id=link.deal_id,
        created_by=UserRef.model_validate(link.created_by),
        created_at=link.created_at,
        expires_at=link.expires_at,
        revoked_at=link.revoked_at,
        sent_via=link.sent_via,
        state=service.link_state(db, link),
        booking=booking_out(active) if active else None,
    )


def slots_out(calendar: availability.Calendar, meeting: MeetingType) -> Slots:
    zone = availability.tz()
    days: dict[date, list[datetime]] = {}
    for slot in availability.slots(calendar, meeting):
        days.setdefault(slot.astimezone(zone).date(), []).append(slot)
    return Slots(
        timezone=zone.key,
        duration_minutes=meeting.duration_minutes,
        days=[Day(date=day, slots=items) for day, items in days.items()],
    )
