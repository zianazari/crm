"""Booking in the staff panel (spec 4.10): availability settings, meeting types, days
off, booking links, and the bookings themselves.

A person edits their own settings; a manager also those of their team members and an
admin anyone's. A link is made by the calendar owner, or by someone who manages them,
for a customer they see in full.
"""

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.modules.auth.deps import DbDep, require_csrf
from app.modules.booking import availability, service
from app.modules.booking.models import (
    AvailabilityException,
    AvailabilityRule,
    Booking,
    BookingLink,
    BookingStatus,
    MeetingType,
)
from app.modules.booking.schemas import (
    BookingOut,
    CancelIn,
    ExceptionIn,
    ExceptionOut,
    LinkCreated,
    LinkIn,
    LinkOut,
    MeetingTypeIn,
    MeetingTypeOut,
    MeetingTypeUpdate,
    SettingsIn,
    SettingsOut,
    Slots,
    parse_hhmm,
)
from app.modules.booking.views import booking_out, link_out, slots_out
from app.modules.crm.access import FORBIDDEN, AccessScope
from app.modules.crm.common import NOT_FOUND, ScopeDep, require_sales_access, unprocessable
from app.modules.crm.models import Customer
from app.modules.crm.schemas import UserRef
from app.modules.identity.models import User
from app.modules.messaging.models import Channel, Purpose
from app.modules.messaging.service import enqueue
from app.modules.sales.models import Deal

router = APIRouter(
    prefix="/booking",
    tags=["booking"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)

UserParam = Annotated[uuid.UUID | None, Query()]


def _target(db: Session, scope: AccessScope, user_id: uuid.UUID | None) -> User:
    """Whose calendar: one's own, or someone the caller manages."""
    if user_id is None or user_id == scope.user.id:
        return scope.user
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="کاربر پیدا نشد.")
    if not scope.can_manage(user.id):
        raise FORBIDDEN
    return user


def _settings_out(db: Session, user: User) -> SettingsOut:
    settings = availability.ensure_settings(db, user.id)
    rules = db.scalars(
        select(AvailabilityRule)
        .where(AvailabilityRule.user_id == user.id)
        .order_by(AvailabilityRule.weekday, AvailabilityRule.start_time)
    )
    types = db.scalars(
        select(MeetingType).where(MeetingType.user_id == user.id).order_by(MeetingType.created_at)
    )
    today = availability.load(db, user.id).start.astimezone(availability.tz()).date()
    exceptions = db.scalars(
        select(AvailabilityException)
        .where(
            or_(AvailabilityException.user_id == user.id, AvailabilityException.user_id.is_(None)),
            AvailabilityException.end_date >= today - timedelta(days=30),
        )
        .order_by(AvailabilityException.start_date)
    )
    return SettingsOut(
        user=UserRef.model_validate(user),
        timezone=availability.tz().key,
        buffer_before_minutes=settings.buffer_before_minutes,
        buffer_after_minutes=settings.buffer_after_minutes,
        min_notice_minutes=settings.min_notice_minutes,
        horizon_days=settings.horizon_days,
        change_deadline_hours=settings.change_deadline_hours,
        rules=[
            {
                "weekday": r.weekday,
                "start": r.start_time.strftime("%H:%M"),
                "end": r.end_time.strftime("%H:%M"),
            }
            for r in rules
        ],
        meeting_types=[MeetingTypeOut.model_validate(t) for t in types],
        exceptions=[
            ExceptionOut(
                id=e.id,
                start_date=e.start_date,
                end_date=e.end_date,
                reason=e.reason,
                organization=e.user_id is None,
            )
            for e in exceptions
        ],
    )


# -- settings --------------------------------------------------------------------------


@router.get("/settings")
def get_settings_(db: DbDep, scope: ScopeDep, user_id: UserParam = None) -> SettingsOut:
    user = _target(db, scope, user_id)
    result = _settings_out(db, user)
    db.commit()  # the defaults, if they were just created
    return result


@router.put("/settings")
def put_settings(
    body: SettingsIn, db: DbDep, scope: ScopeDep, user_id: UserParam = None
) -> SettingsOut:
    user = _target(db, scope, user_id)
    rules = sorted(
        ((r.weekday, parse_hhmm(r.start), parse_hhmm(r.end)) for r in body.rules),
        key=lambda r: (r[0], r[1]),
    )
    for _weekday, start, end in rules:
        if start >= end:
            raise unprocessable("ساعت پایان هر بازه باید بعد از ساعت شروع آن باشد.")
    for (day_a, _, end_a), (day_b, start_b, _) in itertools.pairwise(rules):
        if day_a == day_b and start_b < end_a:
            raise unprocessable("بازه‌های ساعت کاری یک روز با هم هم‌پوشانی دارند.")
    settings = availability.ensure_settings(db, user.id)
    for key in (
        "buffer_before_minutes",
        "buffer_after_minutes",
        "min_notice_minutes",
        "horizon_days",
        "change_deadline_hours",
    ):
        setattr(settings, key, getattr(body, key))
    db.execute(delete(AvailabilityRule).where(AvailabilityRule.user_id == user.id))
    db.add_all(
        AvailabilityRule(user_id=user.id, weekday=w, start_time=s, end_time=e) for w, s, e in rules
    )
    db.flush()
    result = _settings_out(db, user)
    db.commit()
    return result


# -- meeting types ---------------------------------------------------------------------


@router.post("/meeting-types", status_code=status.HTTP_201_CREATED)
def create_meeting_type(
    body: MeetingTypeIn, db: DbDep, scope: ScopeDep, user_id: UserParam = None
) -> MeetingTypeOut:
    user = _target(db, scope, user_id)
    availability.ensure_settings(db, user.id)
    meeting = MeetingType(
        user_id=user.id,
        title=body.title.strip(),
        duration_minutes=body.duration_minutes,
        description=(body.description or "").strip() or None,
    )
    db.add(meeting)
    db.commit()
    return MeetingTypeOut.model_validate(meeting)


@router.patch("/meeting-types/{meeting_type_id}")
def update_meeting_type(
    meeting_type_id: uuid.UUID, body: MeetingTypeUpdate, db: DbDep, scope: ScopeDep
) -> MeetingTypeOut:
    meeting = db.get(MeetingType, meeting_type_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="نوع جلسه پیدا نشد.")
    _target(db, scope, meeting.user_id)
    data = body.model_dump(exclude_unset=True)
    if "description" in data:
        meeting.description = (data.pop("description") or "").strip() or None
    for key, value in data.items():
        if value is not None:
            setattr(meeting, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    return MeetingTypeOut.model_validate(meeting)


# -- days off --------------------------------------------------------------------------


@router.post("/exceptions", status_code=status.HTTP_201_CREATED)
def add_exception(
    body: ExceptionIn, db: DbDep, scope: ScopeDep, user_id: UserParam = None
) -> ExceptionOut:
    if body.end_date < body.start_date:
        raise unprocessable("تاریخ پایان نباید پیش از تاریخ شروع باشد.")
    if (body.end_date - body.start_date).days > 366:
        raise unprocessable("بازه بیش از یک سال است.")
    if body.organization:
        if not scope.is_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="تعطیلات سازمان را فقط ادمین ثبت می‌کند."
            )
        owner: uuid.UUID | None = None
    else:
        owner = _target(db, scope, user_id).id
    row = AvailabilityException(
        user_id=owner,
        start_date=body.start_date,
        end_date=body.end_date,
        reason=body.reason.strip(),
        created_by_id=scope.user.id,
    )
    db.add(row)
    db.commit()
    return ExceptionOut(
        id=row.id,
        start_date=row.start_date,
        end_date=row.end_date,
        reason=row.reason,
        organization=owner is None,
    )


@router.delete("/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_exception(exception_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> None:
    row = db.get(AvailabilityException, exception_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="مورد پیدا نشد.")
    if row.user_id is None:
        if not scope.is_admin:
            raise FORBIDDEN
    else:
        _target(db, scope, row.user_id)
    db.delete(row)
    db.commit()


# -- free time preview -----------------------------------------------------------------


@router.get("/slots")
def preview_slots(meeting_type_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> Slots:
    """What a customer would see for this meeting type right now."""
    meeting = db.get(MeetingType, meeting_type_id)
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="نوع جلسه پیدا نشد.")
    _target(db, scope, meeting.user_id)
    result = slots_out(availability.load(db, meeting.user_id), meeting)
    db.commit()
    return result


# -- links -----------------------------------------------------------------------------


def _customer(db: Session, scope: AccessScope, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NOT_FOUND
    scope.require_full(customer.owner_id)
    return customer


def _invite_text(link: BookingLink, url: str) -> str:
    until = service._local(link.expires_at).split(" ساعت ")[0]
    return (
        f"{link.user.full_name} برای «{link.meeting_type.title}» زمان‌های آزاد خود را "
        f"برایتان فرستاده است. انتخاب زمان تا {until}:\n{url}"
    )


@router.post("/links", status_code=status.HTTP_201_CREATED)
def create_link(body: LinkIn, db: DbDep, scope: ScopeDep) -> LinkCreated:
    customer = _customer(db, scope, body.customer_id)
    if customer.archived_at is not None:
        raise unprocessable("این مشتری بایگانی شده است.")
    meeting = db.get(MeetingType, body.meeting_type_id)
    if meeting is None or not meeting.is_active:
        raise unprocessable("نوع جلسه پیدا نشد یا غیرفعال است.")
    _target(db, scope, meeting.user_id)
    if not meeting.user.is_active:
        raise unprocessable("صاحب این تقویم غیرفعال است.")
    if body.deal_id is not None:
        deal = db.get(Deal, body.deal_id)
        if deal is None or deal.customer_id != customer.id:
            raise unprocessable("این فروش متعلق به همین مشتری نیست.")
    address = None
    if body.send is Channel.SMS:
        address = customer.mobile
    elif body.send is Channel.EMAIL:
        address = customer.email
    if body.send is not None and not address:
        raise unprocessable(
            "برای این مشتری شماره همراه ثبت نشده است."
            if body.send is Channel.SMS
            else "برای این مشتری ایمیل ثبت نشده است."
        )
    token = service.new_token()
    link = BookingLink(
        token_hash=service.token_hash(token),
        user_id=meeting.user_id,
        customer_id=customer.id,
        deal_id=body.deal_id,
        meeting_type_id=meeting.id,
        created_by_id=scope.user.id,
        expires_at=datetime.now(UTC) + timedelta(days=body.expires_in_days),
        sent_via=body.send,
    )
    db.add(link)
    db.flush()
    db.refresh(link)
    url = service.link_url(token)
    if body.send is not None and address:
        enqueue(
            db,
            body.send,
            Purpose.NOTIFICATION,
            address,
            subject="انتخاب زمان جلسه" if body.send is Channel.EMAIL else None,
            body=_invite_text(link, url),
        )
    db.commit()
    return LinkCreated(link=link_out(db, link), url=url)


@router.get("/links")
def list_links(customer_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> list[LinkOut]:
    _customer(db, scope, customer_id)
    links = db.scalars(
        select(BookingLink)
        .where(BookingLink.customer_id == customer_id)
        .order_by(BookingLink.created_at.desc())
        .limit(50)
    )
    return [link_out(db, link) for link in links]


@router.post("/links/{link_id}/revoke")
def revoke_link(link_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> LinkOut:
    """The link stops working; a booking already made with it stays."""
    link = db.get(BookingLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="لینک پیدا نشد.")
    _customer(db, scope, link.customer_id)
    if link.revoked_at is None:
        link.revoked_at = datetime.now(UTC)
        db.commit()
    return link_out(db, link)


# -- bookings --------------------------------------------------------------------------


@router.get("/bookings")
def list_bookings(
    db: DbDep,
    scope: ScopeDep,
    customer_id: uuid.UUID | None = None,
    upcoming: bool = False,
) -> list[BookingOut]:
    query = select(Booking).where(Booking.status != BookingStatus.RESCHEDULED)
    if customer_id is not None:
        _customer(db, scope, customer_id)
        query = query.where(Booking.customer_id == customer_id)
    else:
        ids = scope.owner_ids()
        if ids is not None:
            query = query.where(Booking.user_id.in_(ids))
    if upcoming:
        query = query.where(
            Booking.status == BookingStatus.CONFIRMED, Booking.end_at > datetime.now(UTC)
        )
        query = query.order_by(Booking.start_at)
    else:
        query = query.order_by(Booking.start_at.desc())
    return [booking_out(b) for b in db.scalars(query.limit(100))]


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: uuid.UUID, body: CancelIn, db: DbDep, scope: ScopeDep) -> BookingOut:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update(of=Booking))
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="رزرو پیدا نشد.")
    if not (
        scope.has_full_access(booking.user_id) or scope.has_full_access(booking.customer.owner_id)
    ):
        raise FORBIDDEN
    if booking.status is not BookingStatus.CONFIRMED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این رزرو قبلاً لغو شده است.")
    service.cancel(db, booking, body.reason, by_user=scope.user.id)
    db.commit()
    db.refresh(booking)
    return booking_out(booking)
