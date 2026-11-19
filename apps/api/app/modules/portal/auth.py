"""Customer portal login and sessions (spec 4.9).

The code is sent only to an address that has portal access; the response is the same
either way. Portal cookies (``crm_portal``, ``crm_portal_csrf``) are separate from staff
cookies, and every state-changing portal request needs the CSRF header.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.audit.service import audit
from app.modules.auth.deps import DbDep, SettingsDep, client_ip, get_otp_service
from app.modules.auth.otp import InvalidDestinationError, OtpService, RateLimitedError
from app.modules.auth.schemas import OtpRequestIn, OtpRequestOut, OtpVerifyIn
from app.modules.auth.sender import Channel as OtpChannel
from app.modules.messaging.models import Channel
from app.modules.portal.models import PortalIdentity, PortalSession

SESSION_COOKIE = "crm_portal"
CSRF_COOKIE = "crm_portal_csrf"
CSRF_HEADER = "X-CSRF-Token"
SESSION_DAYS = 30
IDLE_DAYS = 7

_UNAUTHORIZED = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="لطفاً دوباره وارد شوید.")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def portal_lookup(db: Session, channel: OtpChannel, destination: str) -> uuid.UUID | None:
    """The active portal identity for this address, if its customer is still current."""
    identity = db.scalar(
        select(PortalIdentity).where(
            PortalIdentity.channel == Channel(channel.value),
            PortalIdentity.address == destination,
            PortalIdentity.is_active.is_(True),
        )
    )
    if identity is None or identity.customer.archived_at is not None:
        return None
    return identity.id


def revoke_sessions(db: Session, identity_id: uuid.UUID) -> None:
    db.execute(
        update(PortalSession)
        .where(PortalSession.identity_id == identity_id, PortalSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


# -- the current customer ------------------------------------------------------------------


@dataclass(frozen=True)
class PortalUser:
    identity: PortalIdentity
    session_id: uuid.UUID

    @property
    def customer_id(self) -> uuid.UUID:
        return self.identity.customer_id


def current_portal_user(request: Request, db: DbDep) -> PortalUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _UNAUTHORIZED
    now = datetime.now(UTC)
    session = db.scalar(select(PortalSession).where(PortalSession.token_hash == _hash(token)))
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.last_seen_at <= now - timedelta(days=IDLE_DAYS)
        or not session.identity.is_active
        or session.identity.customer.archived_at is not None
    ):
        raise _UNAUTHORIZED
    if session.last_seen_at <= now - timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return PortalUser(identity=session.identity, session_id=session.id)


PortalUserDep = Annotated[PortalUser, Depends(current_portal_user)]


def require_portal_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="درخواست نامعتبر است.")


def _set_cookies(response: Response, settings: Settings, token: str) -> None:
    common = {
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain,
        "path": "/",
        "max_age": SESSION_DAYS * 86400,
    }
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)  # type: ignore[arg-type]
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), httponly=False, **common)  # type: ignore[arg-type]


def _clear_cookies(response: Response, settings: Settings) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name, path="/", domain=settings.cookie_domain, secure=settings.cookie_secure
        )


# -- endpoints ---------------------------------------------------------------------------


router = APIRouter(prefix="/portal", tags=["portal"])

OtpServiceDep = Annotated[OtpService, Depends(get_otp_service)]


class PortalMe(BaseModel):
    customer_name: str
    channel: Channel
    address: str


def me_of(identity: PortalIdentity) -> PortalMe:
    return PortalMe(
        customer_name=identity.customer.full_name,
        channel=identity.channel,
        address=identity.address,
    )


def _too_many(exc: RateLimitedError) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail="تعداد درخواست‌ها زیاد است. کمی بعد دوباره تلاش کنید.",
        headers={"Retry-After": str(exc.retry_after)},
    )


@router.post("/auth/otp/request", status_code=status.HTTP_202_ACCEPTED)
def request_code(
    body: OtpRequestIn, request: Request, db: DbDep, otp: OtpServiceDep
) -> OtpRequestOut:
    """Sends a code only to an address with portal access; the answer never says which."""
    try:
        challenge = otp.request(
            db,
            body.channel,
            body.destination,
            client_ip(request),
            audience="portal",
            lookup=portal_lookup,
        )
    except InvalidDestinationError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="شماره موبایل یا ایمیل معتبر نیست."
        ) from None
    except RateLimitedError as exc:
        raise _too_many(exc) from None
    return OtpRequestOut(
        challenge_id=challenge.challenge_id,
        expires_in=challenge.expires_in,
        resend_after=challenge.resend_after,
    )


@router.post("/auth/otp/verify")
def verify_code(
    body: OtpVerifyIn,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    otp: OtpServiceDep,
) -> PortalMe:
    try:
        identity_id = otp.verify(
            body.challenge_id, body.code, client_ip(request), audience="portal"
        )
    except RateLimitedError as exc:
        raise _too_many(exc) from None
    identity = db.get(PortalIdentity, identity_id) if identity_id else None
    if identity is None or not identity.is_active or identity.customer.archived_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="کد نادرست یا منقضی شده است.")
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(
        PortalSession(
            identity_id=identity.id,
            token_hash=_hash(token),
            expires_at=now + timedelta(days=SESSION_DAYS),
            last_seen_at=now,
            user_agent=(request.headers.get("user-agent") or "")[:300] or None,
            ip=client_ip(request),
        )
    )
    identity.last_login_at = now
    audit(
        db,
        "portal.login",
        None,
        "portal_identity",
        identity.id,
        {"customer_id": str(identity.customer_id)},
        client_ip(request),
    )
    db.commit()
    _set_cookies(response, settings, token)
    return me_of(identity)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: DbDep, settings: SettingsDep) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(
            update(PortalSession)
            .where(PortalSession.token_hash == _hash(token), PortalSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_cookies(response, settings)
    return response


@router.get("/me")
def me(user: PortalUserDep) -> PortalMe:
    return me_of(user.identity)
