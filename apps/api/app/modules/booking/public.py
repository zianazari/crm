"""The customer's booking page behind a link (spec 4.10; criterion 18).

Anyone holding the link sees the meeting, the staff member's name and free times, never
the customer's record. Booking, moving or canceling needs the customer verified first:
either a portal session of the same customer, or a one-time code sent to the mobile or
email on file for that customer (the answer to a code request never says whether the
address matched). The verification lives in Redis for two hours and is bound to the
link; state-changing requests also need the CSRF header matching its cookie.
"""

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.modules.auth.deps import DbDep, SettingsDep, client_ip, get_otp_service
from app.modules.auth.otp import InvalidDestinationError, OtpService, RateLimitedError
from app.modules.auth.schemas import OtpRequestIn, OtpRequestOut, OtpVerifyIn
from app.modules.auth.sender import Channel as OtpChannel
from app.modules.booking import availability, service
from app.modules.booking.models import Booking, BookingLink
from app.modules.booking.schemas import CancelIn, MeetingTypeOut, Slots, StartIn
from app.modules.booking.views import slots_out
from app.modules.messaging.models import Channel
from app.modules.portal import auth as portal_auth
from app.modules.portal.models import PortalIdentity

router = APIRouter(prefix="/book", tags=["booking"])

COOKIE = "crm_booking"
CSRF_COOKIE = "crm_booking_csrf"
VERIFIED_SECONDS = 2 * 3600

_GONE = {
    "expired": "مهلت این لینک تمام شده است. برای لینک تازه با کارشناس خود تماس بگیرید.",
    "revoked": "این لینک دیگر فعال نیست. برای لینک تازه با کارشناس خود تماس بگیرید.",
}


def _key(cookie: str) -> str:
    return f"booking:verified:{hashlib.sha256(cookie.encode()).hexdigest()}"


def _load(db: Session, token: str) -> BookingLink:
    link = db.scalar(select(BookingLink).where(BookingLink.token_hash == service.token_hash(token)))
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="این لینک معتبر نیست.")
    return link


@dataclass(frozen=True)
class Contact:
    channel: Channel
    address: str
    csrf_cookie: str


def _contact(request: Request, db: Session, redis: Redis, link: BookingLink) -> Contact | None:
    cookie = request.cookies.get(COOKIE)
    if cookie:
        raw = redis.get(_key(cookie))
        if raw:
            data = json.loads(raw)
            if data["link"] == str(link.id):
                return Contact(Channel(data["channel"]), data["address"], CSRF_COOKIE)
    if request.cookies.get(portal_auth.SESSION_COOKIE):
        try:
            user = portal_auth.current_portal_user(request, db)
        except HTTPException:
            return None
        if user.customer_id == link.customer_id:
            identity = user.identity
            return Contact(identity.channel, identity.address, portal_auth.CSRF_COOKIE)
    return None


def _require_contact(request: Request, db: Session, redis: Redis, link: BookingLink) -> Contact:
    contact = _contact(request, db, redis, link)
    if contact is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="ابتدا هویت خود را تأیید کنید.")
    header = request.headers.get(portal_auth.CSRF_HEADER, "")
    cookie = request.cookies.get(contact.csrf_cookie, "")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="درخواست نامعتبر است.")
    return contact


RedisDep = Annotated[Redis, Depends(get_redis)]
OtpServiceDep = Annotated[OtpService, Depends(get_otp_service)]


class BookingView(BaseModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    can_change: bool
    change_until: datetime


class LinkView(BaseModel):
    state: str  # open, booked, expired, revoked
    staff_name: str
    meeting: MeetingTypeOut
    timezone: str
    expires_at: datetime
    change_deadline_hours: int
    verified: bool
    # Only once verified: the confirmed booking made with this link.
    booking: BookingView | None


def _view(db: Session, link: BookingLink, verified: bool) -> LinkView:
    settings = availability.ensure_settings(db, link.user_id)
    active = service.active_booking(db, link)
    booking = None
    if verified and active is not None:
        booking = BookingView(
            id=active.id,
            start_at=active.start_at,
            end_at=active.end_at,
            can_change=service.can_change(db, active),
            change_until=service.change_deadline(db, active),
        )
    return LinkView(
        state=service.link_state(db, link),
        staff_name=link.user.full_name,
        meeting=MeetingTypeOut.model_validate(link.meeting_type),
        timezone=availability.tz().key,
        expires_at=link.expires_at,
        change_deadline_hours=settings.change_deadline_hours,
        verified=verified,
        booking=booking,
    )


@router.get("/{token}")
def view_link(token: str, request: Request, db: DbDep, redis: RedisDep) -> LinkView:
    link = _load(db, token)
    result = _view(db, link, _contact(request, db, redis, link) is not None)
    db.commit()
    return result


@router.get("/{token}/slots")
def link_slots(token: str, db: DbDep) -> Slots:
    """Free times. With a booking already made, the times it could move to."""
    link = _load(db, token)
    state = service.link_state(db, link)
    if state in _GONE:
        raise HTTPException(status.HTTP_410_GONE, detail=_GONE[state])
    active = service.active_booking(db, link)
    calendar = availability.load(db, link.user_id, ignore_booking=active)
    result = slots_out(calendar, link.meeting_type)
    db.commit()
    return result


# -- verification ------------------------------------------------------------------------


def _subject(link: BookingLink, channel: OtpChannel, destination: str) -> uuid.UUID:
    return uuid.uuid5(link.id, f"{channel.value}:{destination}")


def _matches(db: Session, link: BookingLink, channel: OtpChannel, destination: str) -> bool:
    customer = link.customer
    if (channel is OtpChannel.SMS and customer.mobile == destination) or (
        channel is OtpChannel.EMAIL and customer.email == destination
    ):
        return True
    return (
        db.scalar(
            select(PortalIdentity.id).where(
                PortalIdentity.customer_id == customer.id,
                PortalIdentity.channel == Channel(channel.value),
                PortalIdentity.address == destination,
                PortalIdentity.is_active.is_(True),
            )
        )
        is not None
    )


def _pending_key(subject: uuid.UUID) -> str:
    return f"booking:subject:{subject}"


@router.post("/{token}/otp/request", status_code=status.HTTP_202_ACCEPTED)
def request_code(
    token: str,
    body: OtpRequestIn,
    request: Request,
    db: DbDep,
    redis: RedisDep,
    otp: OtpServiceDep,
) -> OtpRequestOut:
    link = _load(db, token)
    if link.revoked_at is not None:
        raise HTTPException(status.HTTP_410_GONE, detail=_GONE["revoked"])

    def lookup(db_: Session, channel: OtpChannel, destination: str) -> uuid.UUID | None:
        if not _matches(db_, link, channel, destination):
            return None
        subject = _subject(link, channel, destination)
        redis.set(
            _pending_key(subject),
            json.dumps({"link": str(link.id), "channel": channel.value, "address": destination}),
            ex=otp.settings.otp_ttl_seconds + 60,
        )
        return subject

    try:
        challenge = otp.request(
            db,
            body.channel,
            body.destination,
            client_ip(request),
            audience="booking",
            lookup=lookup,
        )
    except InvalidDestinationError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="شماره موبایل یا ایمیل معتبر نیست."
        ) from None
    except RateLimitedError as exc:
        raise portal_auth._too_many(exc) from None
    return OtpRequestOut(
        challenge_id=challenge.challenge_id,
        expires_in=challenge.expires_in,
        resend_after=challenge.resend_after,
    )


@router.post("/{token}/otp/verify")
def verify_code(
    token: str,
    body: OtpVerifyIn,
    request: Request,
    response: Response,
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
    otp: OtpServiceDep,
) -> LinkView:
    link = _load(db, token)
    try:
        subject = otp.verify(body.challenge_id, body.code, client_ip(request), audience="booking")
    except RateLimitedError as exc:
        raise portal_auth._too_many(exc) from None
    raw = redis.get(_pending_key(subject)) if subject else None
    data = json.loads(raw) if raw else None
    if data is None or data["link"] != str(link.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="کد نادرست یا منقضی شده است.")
    cookie = secrets.token_urlsafe(32)
    redis.set(_key(cookie), raw, ex=VERIFIED_SECONDS)  # type: ignore[arg-type]
    redis.delete(_pending_key(subject))  # type: ignore[arg-type]
    common = {
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain,
        "path": "/",
        "max_age": VERIFIED_SECONDS,
    }
    response.set_cookie(COOKIE, cookie, httponly=True, **common)  # type: ignore[arg-type]
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), httponly=False, **common)  # type: ignore[arg-type]
    result = _view(db, link, True)
    db.commit()
    return result


# -- book, move, cancel -----------------------------------------------------------------


@router.post("/{token}/book", status_code=status.HTTP_201_CREATED)
def make_booking(
    token: str, body: StartIn, request: Request, db: DbDep, redis: RedisDep
) -> LinkView:
    link = _load(db, token)
    contact = _require_contact(request, db, redis, link)
    state = service.link_state(db, link)
    if state in _GONE:
        raise HTTPException(status.HTTP_410_GONE, detail=_GONE[state])
    if state == "booked":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="با این لینک قبلاً جلسه‌ای رزرو شده است."
        )
    try:
        service.book(
            db, link, body.start_at, (contact.channel, contact.address), service.link_url(token)
        )
    except service.SlotTakenError:
        db.rollback()
        raise service.raise_taken() from None
    db.commit()
    return _view(db, link, True)


def _active_for_change(db: Session, link: BookingLink) -> Booking:
    if link.revoked_at is not None:
        raise HTTPException(status.HTTP_410_GONE, detail=_GONE["revoked"])
    booking = service.active_booking(db, link)
    if booking is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="رزرو فعالی برای این لینک نیست.")
    if not service.can_change(db, booking, datetime.now(UTC)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="مهلت لغو یا تغییر این جلسه گذشته است. با کارشناس خود تماس بگیرید.",
        )
    return booking


@router.post("/{token}/reschedule")
def move_booking(
    token: str, body: StartIn, request: Request, db: DbDep, redis: RedisDep
) -> LinkView:
    link = _load(db, token)
    _require_contact(request, db, redis, link)
    booking = _active_for_change(db, link)
    try:
        service.reschedule(db, booking, body.start_at, service.link_url(token))
    except service.SlotTakenError:
        db.rollback()
        raise service.raise_taken() from None
    db.commit()
    return _view(db, link, True)


@router.post("/{token}/cancel")
def cancel_booking(
    token: str, body: CancelIn, request: Request, db: DbDep, redis: RedisDep
) -> LinkView:
    link = _load(db, token)
    _require_contact(request, db, redis, link)
    booking = _active_for_change(db, link)
    service.cancel(db, booking, body.reason)
    db.commit()
    return _view(db, link, True)
