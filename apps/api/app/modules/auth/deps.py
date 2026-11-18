import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.redis import get_redis
from app.db.session import get_db
from app.modules.auth.otp import OtpService
from app.modules.auth.sender import OtpSender, build_otp_sender
from app.modules.auth.sessions import IssuedTokens, SessionService, is_session_live
from app.modules.auth.tokens import InvalidTokenError, decode_access_token
from app.modules.identity.models import User

ACCESS_COOKIE = "crm_access"
REFRESH_COOKIE = "crm_refresh"
CSRF_COOKIE = "crm_csrf"
CSRF_HEADER = "X-CSRF-Token"

SettingsDep = Annotated[Settings, Depends(get_settings)]
RedisDep = Annotated[Redis, Depends(get_redis)]
DbDep = Annotated[Session, Depends(get_db)]


def get_otp_sender(settings: SettingsDep, db: DbDep, redis: RedisDep) -> OtpSender:
    return build_otp_sender(settings, db, redis)


def get_otp_service(
    redis: RedisDep, settings: SettingsDep, sender: Annotated[OtpSender, Depends(get_otp_sender)]
) -> OtpService:
    return OtpService(redis, settings, sender)


def get_session_service(db: DbDep, redis: RedisDep, settings: SettingsDep) -> SessionService:
    return SessionService(db, redis, settings)


def client_ip(request: Request) -> str:
    # Behind a reverse proxy this must come from a trusted forwarded header (set at deploy).
    return request.client.host if request.client else "unknown"


def set_auth_cookies(response: Response, settings: Settings, tokens: IssuedTokens) -> None:
    common = {
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain,
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        max_age=settings.access_token_ttl_seconds,
        httponly=True,
        **common,  # type: ignore[arg-type]
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        **common,  # type: ignore[arg-type]
    )
    # Readable by the web app so it can echo it in the X-CSRF-Token header (double submit).
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=False,
        **common,  # type: ignore[arg-type]
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name, path="/", domain=settings.cookie_domain, secure=settings.cookie_secure
        )


def require_csrf(request: Request) -> None:
    """Rejects state-changing cookie-authenticated requests without a matching CSRF token."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="درخواست نامعتبر است.")


_UNAUTHORIZED = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="لطفاً دوباره وارد شوید.")


@dataclass(frozen=True)
class CurrentUser:
    user: User
    session_id: uuid.UUID


def get_current_user(
    request: Request, db: DbDep, redis: RedisDep, settings: SettingsDep
) -> CurrentUser:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise _UNAUTHORIZED
    try:
        claims = decode_access_token(settings, token)
    except InvalidTokenError:
        raise _UNAUTHORIZED from None
    # Revocation check: logout/deactivation removes the key immediately.
    if not is_session_live(redis, claims.session_id):
        raise _UNAUTHORIZED
    user = db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return CurrentUser(user=user, session_id=claims.session_id)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
