"""Profile photos (shown wherever a person appears, as in the design concepts).

Each person sets or removes their own photo. The browser crops and shrinks it first;
the API only accepts a small WebP, JPEG or PNG and checks the file's own signature,
not just the declared type. Photos are served to signed-in staff under a versioned
URL, so they can be cached for good.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete

from app.modules.auth.deps import CurrentUserDep, DbDep, require_csrf
from app.modules.auth.schemas import UserOut
from app.modules.identity.models import User, UserAvatar

router = APIRouter(prefix="/users", tags=["administration"], dependencies=[Depends(require_csrf)])

MAX_BYTES = 200 * 1024

_SIGNATURES = {
    "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}


def _me_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/{user_id}/avatar", response_class=Response)
def get_avatar(user_id: uuid.UUID, db: DbDep, _: CurrentUserDep) -> Response:
    avatar = db.get(UserAvatar, user_id)
    if avatar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="تصویری ثبت نشده است.")
    return Response(
        avatar.content,
        media_type=avatar.content_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@router.put("/me/avatar")
async def set_avatar(request: Request, db: DbDep, current: CurrentUserDep) -> UserOut:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    check = _SIGNATURES.get(content_type)
    if check is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="فقط تصویر WebP، JPEG یا PNG."
        )
    body = await request.body()
    if len(body) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, detail="حجم تصویر بیش از ۲۰۰ کیلوبایت است."
        )
    if not body or not check(body):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="فایل تصویر معتبر نیست.")
    user = current.user
    avatar = db.get(UserAvatar, user.id)
    if avatar is None:
        db.add(UserAvatar(user_id=user.id, content=body, content_type=content_type))
    else:
        avatar.content, avatar.content_type = body, content_type
        avatar.updated_at = datetime.now(UTC)
    user.avatar_version = (user.avatar_version or 0) + 1
    db.commit()
    db.refresh(user)
    return _me_out(user)


@router.delete("/me/avatar")
def remove_avatar(db: DbDep, current: CurrentUserDep) -> UserOut:
    user = current.user
    db.execute(delete(UserAvatar).where(UserAvatar.user_id == user.id))
    user.avatar_version = None
    db.commit()
    db.refresh(user)
    return _me_out(user)
