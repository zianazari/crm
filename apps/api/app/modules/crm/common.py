import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal, Protocol, cast
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.normalize import normalize_email, normalize_mobile
from app.modules.auth.deps import CurrentUserDep, DbDep
from app.modules.automation.events import emit
from app.modules.crm.access import AccessScope, build_scope
from app.modules.crm.models import Customer, Lead, LeadSource, OwnershipHistory, Tag
from app.modules.crm.schemas import DuplicateConflict, DuplicateMatch, UserRef
from app.modules.identity.models import User
from app.modules.notifications.service import record_assigned


def get_scope(current: CurrentUserDep, db: DbDep) -> AccessScope:
    return build_scope(db, current.user)


ScopeDep = Annotated[AccessScope, Depends(get_scope)]

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="پرونده پیدا نشد.")


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


# -- contact fields --------------------------------------------------------


def clean_mobile(value: str | None) -> str | None:
    if value is None:
        return None
    mobile = normalize_mobile(value)
    if mobile is None:
        raise unprocessable("شماره موبایل معتبر نیست.")
    return mobile


def clean_email(value: str | None) -> str | None:
    if value is None:
        return None
    email = normalize_email(value)
    if email is None:
        raise unprocessable("ایمیل معتبر نیست.")
    return email


# -- duplicates ------------------------------------------------------------


def find_duplicates(
    db: Session,
    scope: AccessScope,
    mobile: str | None,
    email: str | None,
    exclude_id: uuid.UUID | None = None,
) -> list[DuplicateMatch]:
    """Active customers and open leads sharing a normalized mobile or email.

    Matches outside the user's scope are returned in limited form (name and owner) so
    the user can refer to the owner instead of creating a second record.
    """
    if not mobile and not email:
        return []
    matches: list[DuplicateMatch] = []
    models: tuple[tuple[Literal["customer", "lead"], type[Customer] | type[Lead]], ...] = (
        ("customer", Customer),
        ("lead", Lead),
    )
    for kind, model in models:
        conditions = []
        if mobile:
            conditions.append(model.mobile == mobile)
        if email:
            conditions.append(model.email == email)
        query = select(model).where(or_(*conditions), model.archived_at.is_(None))
        if model is Lead:
            query = query.where(Lead.status != "converted")
        if exclude_id is not None:
            query = query.where(model.id != exclude_id)
        rows = cast("Sequence[Customer | Lead]", db.scalars(query.limit(10)).all())
        for row in rows:
            matched: list[Literal["mobile", "email"]] = []
            if mobile and row.mobile == mobile:
                matched.append("mobile")
            if email and row.email == email:
                matched.append("email")
            matches.append(
                DuplicateMatch(
                    kind=kind,
                    id=row.id,
                    full_name=row.full_name,
                    owner=UserRef.model_validate(row.owner),
                    matched_on=matched,
                    access="full" if scope.has_full_access(row.owner_id) else "limited",
                )
            )
    return matches


def duplicate_response(matches: list[DuplicateMatch]) -> JSONResponse:
    body = DuplicateConflict(detail="پرونده‌ای با همین موبایل یا ایمیل وجود دارد.", matches=matches)
    return JSONResponse(body.model_dump(mode="json"), status_code=status.HTTP_409_CONFLICT)


# -- reference data --------------------------------------------------------


def resolve_tags(db: Session, tag_ids: list[uuid.UUID]) -> list[Tag]:
    if not tag_ids:
        return []
    tags = list(db.scalars(select(Tag).where(Tag.id.in_(set(tag_ids)))))
    if len(tags) != len(set(tag_ids)):
        raise unprocessable("برچسب انتخاب‌شده معتبر نیست.")
    return tags


def check_source(db: Session, source_id: uuid.UUID | None) -> None:
    if source_id is None:
        return
    source = db.get(LeadSource, source_id)
    if source is None or not source.is_active:
        raise unprocessable("منبع جذب معتبر نیست.")


def resolve_owner(db: Session, scope: AccessScope, owner_id: uuid.UUID | None) -> User:
    if owner_id is None or owner_id == scope.user.id:
        return scope.user
    owner = db.get(User, owner_id)
    if owner is None or not scope.can_assign_to(owner):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="انتساب به این کاربر مجاز نیست.")
    return owner


# -- ownership & archive ---------------------------------------------------


class OwnedRecord(Protocol):
    """Any owned, archivable record: lead, customer or deal."""

    id: uuid.UUID
    owner_id: uuid.UUID
    owner: User
    archived_at: datetime | None
    archived_by_id: uuid.UUID | None


def change_owner(
    db: Session,
    scope: AccessScope,
    record: OwnedRecord,
    entity_type: str,
    new_owner_id: uuid.UUID,
    reason: str | None,
) -> None:
    scope.require_manage(record.owner_id)
    new_owner = db.get(User, new_owner_id)
    if new_owner is None or not scope.can_assign_to(new_owner):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="انتساب به این کاربر مجاز نیست.")
    if new_owner.id == record.owner_id:
        return
    db.add(
        OwnershipHistory(
            entity_type=entity_type,
            entity_id=record.id,
            from_user_id=record.owner_id,
            to_user_id=new_owner.id,
            changed_by_id=scope.user.id,
            reason=reason,
        )
    )
    previous_owner = record.owner_id
    record.owner_id = new_owner.id
    record.owner = new_owner
    emit(
        db,
        "record.assigned",
        entity_type,
        record.id,
        {"from": str(previous_owner), "to": str(new_owner.id)},
    )
    if new_owner.id != scope.user.id:
        name = str(getattr(record, "full_name", None) or getattr(record, "title", ""))
        record_assigned(
            db, new_owner.id, scope.user.full_name, entity_type, record.id, name, reason
        )


def archive(scope: AccessScope, record: OwnedRecord) -> None:
    scope.require_manage(record.owner_id)
    if record.archived_at is None:
        record.archived_at = datetime.now(UTC)
        record.archived_by_id = scope.user.id


def restore(scope: AccessScope, record: OwnedRecord) -> None:
    scope.require_manage(record.owner_id)
    record.archived_at = None
    record.archived_by_id = None


# -- listing ---------------------------------------------------------------


def day_bounds(
    day_from: date | None, day_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """Inclusive calendar days in the organization's time zone, as UTC instants."""
    tz = ZoneInfo(get_settings().timezone)
    if day_from and day_to and day_from > day_to:
        raise unprocessable("تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد.")
    start = datetime.combine(day_from, time.min, tz) if day_from else None
    end = datetime.combine(day_to + timedelta(days=1), time.min, tz) if day_to else None
    return start, end


def search_condition(model: type[Customer] | type[Lead], q: str) -> ColumnElement[bool]:
    """Name matches anywhere; contact fields only on an exact normalized value, so a
    partial number cannot be used to fish for other people's contacts."""
    conditions: list[ColumnElement[bool]] = [model.full_name.icontains(q, autoescape=True)]
    if (mobile := normalize_mobile(q)) is not None:
        conditions.append(model.mobile == mobile)
    if (email := normalize_email(q)) is not None:
        conditions.append(model.email == email)
    return or_(*conditions)


def paginate[T](db: Session, query: Select[T], page: int, page_size: int) -> tuple[list[T], int]:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = list(db.scalars(query.limit(page_size).offset((page - 1) * page_size)).unique())
    return rows, total
