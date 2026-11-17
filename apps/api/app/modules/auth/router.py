from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.modules.auth.deps import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    CurrentUserDep,
    DbDep,
    SettingsDep,
    clear_auth_cookies,
    client_ip,
    get_otp_service,
    get_session_service,
    require_csrf,
    set_auth_cookies,
)
from app.modules.auth.otp import InvalidDestinationError, OtpService, RateLimitedError
from app.modules.auth.schemas import OtpRequestIn, OtpRequestOut, OtpVerifyIn, UserOut
from app.modules.auth.sessions import InvalidRefreshTokenError, SessionService
from app.modules.auth.tokens import InvalidTokenError, decode_access_token
from app.modules.identity.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

OtpServiceDep = Annotated[OtpService, Depends(get_otp_service)]
SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


def _too_many(exc: RateLimitedError) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail="تعداد درخواست‌ها زیاد است. کمی بعد دوباره تلاش کنید.",
        headers={"Retry-After": str(exc.retry_after)},
    )


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED)
def request_otp(
    body: OtpRequestIn, request: Request, db: DbDep, otp: OtpServiceDep
) -> OtpRequestOut:
    """Sends a 5-digit code if the destination belongs to an active user.

    The response is the same whether or not an account exists.
    """
    try:
        challenge = otp.request(db, body.channel, body.destination, client_ip(request))
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


@router.post("/otp/verify")
def verify_otp(
    body: OtpVerifyIn,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    otp: OtpServiceDep,
    sessions: SessionServiceDep,
) -> UserOut:
    try:
        user_id = otp.verify(body.challenge_id, body.code, client_ip(request))
    except RateLimitedError as exc:
        raise _too_many(exc) from None
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="کد نادرست یا منقضی شده است.")

    tokens = sessions.create(user, request.headers.get("user-agent"), client_ip(request))
    set_auth_cookies(response, settings, tokens)
    return UserOut.model_validate(user)


@router.post("/refresh", response_model=UserOut, dependencies=[Depends(require_csrf)])
def refresh(
    request: Request, response: Response, settings: SettingsDep, sessions: SessionServiceDep
) -> UserOut | JSONResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    try:
        if not token:
            raise InvalidRefreshTokenError("missing")
        tokens = sessions.rotate(token)
    except InvalidRefreshTokenError:
        failed = JSONResponse(
            {"detail": "لطفاً دوباره وارد شوید."}, status_code=status.HTTP_401_UNAUTHORIZED
        )
        clear_auth_cookies(failed, settings)
        return failed
    set_auth_cookies(response, settings, tokens)
    return UserOut.model_validate(tokens.user)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
def logout(
    request: Request, response: Response, settings: SettingsDep, sessions: SessionServiceDep
) -> None:
    """Ends the session even if the access token has already expired."""
    access = request.cookies.get(ACCESS_COOKIE)
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    session_id = None
    if access:
        try:
            session_id = decode_access_token(settings, access).session_id
        except InvalidTokenError:
            session_id = None
    if session_id is not None:
        sessions.revoke(session_id, "logout")
    elif refresh_token:
        sessions.revoke_by_refresh_token(refresh_token, "logout")
    clear_auth_cookies(response, settings)


@router.get("/me")
def me(current: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(current.user)
