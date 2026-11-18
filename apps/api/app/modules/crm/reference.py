"""Lead sources, tags, assignable users and duplicate checks."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.audit.service import audit
from app.modules.auth.deps import DbDep, require_csrf
from app.modules.crm.common import (
    NOT_FOUND,
    ScopeDep,
    clean_email,
    clean_mobile,
    find_duplicates,
)
from app.modules.crm.models import LeadSource, Tag
from app.modules.crm.schemas import DuplicateMatch, LeadSourceIn, LeadSourceOut, Ref, TagIn, UserRef
from app.modules.identity.models import User

router = APIRouter(tags=["reference"], dependencies=[Depends(require_csrf)])

_ADMIN_ONLY = HTTPException(status.HTTP_403_FORBIDDEN, detail="فقط ادمین این تنظیم را تغییر می‌دهد.")
_EXISTS = HTTPException(status.HTTP_409_CONFLICT, detail="این نام قبلاً ثبت شده است.")


@router.get("/lead-sources")
def list_sources(db: DbDep, _: ScopeDep, include_inactive: bool = False) -> list[LeadSourceOut]:
    query = select(LeadSource).order_by(LeadSource.sort_order, LeadSource.name)
    if not include_inactive:
        query = query.where(LeadSource.is_active.is_(True))
    return [LeadSourceOut.model_validate(s) for s in db.scalars(query)]


@router.post("/lead-sources", status_code=status.HTTP_201_CREATED)
def create_source(body: LeadSourceIn, db: DbDep, scope: ScopeDep) -> LeadSourceOut:
    if not scope.is_admin:
        raise _ADMIN_ONLY
    source = LeadSource(**body.model_dump())
    db.add(source)
    try:
        db.flush()
        audit(db, "source.created", scope.user.id, "lead_source", source.id, body.model_dump())
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _EXISTS from None
    return LeadSourceOut.model_validate(source)


@router.patch("/lead-sources/{source_id}")
def update_source(
    source_id: uuid.UUID, body: LeadSourceIn, db: DbDep, scope: ScopeDep
) -> LeadSourceOut:
    if not scope.is_admin:
        raise _ADMIN_ONLY
    source = db.get(LeadSource, source_id)
    if source is None:
        raise NOT_FOUND
    audit(db, "source.updated", scope.user.id, "lead_source", source.id, body.model_dump())
    for key, value in body.model_dump().items():
        setattr(source, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _EXISTS from None
    return LeadSourceOut.model_validate(source)


@router.get("/tags")
def list_tags(
    db: DbDep, _: ScopeDep, q: Annotated[str | None, Query(max_length=50)] = None
) -> list[Ref]:
    query = select(Tag).order_by(Tag.name).limit(100)
    if q and q.strip():
        query = query.where(Tag.name.icontains(q.strip(), autoescape=True))
    return [Ref.model_validate(t) for t in db.scalars(query)]


@router.post("/tags", status_code=status.HTTP_201_CREATED)
def create_tag(body: TagIn, db: DbDep, _: ScopeDep) -> Ref:
    name = body.name.strip()
    existing = db.scalar(select(Tag).where(func.lower(Tag.name) == name.lower()))
    if existing is not None:
        return Ref.model_validate(existing)
    tag = Tag(name=name)
    db.add(tag)
    db.commit()
    return Ref.model_validate(tag)


@router.get("/users/assignable")
def assignable_users(db: DbDep, scope: ScopeDep) -> list[UserRef]:
    """Users the current user may make owner of a record."""
    query = select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    if scope.is_manager:
        query = query.where(User.id.in_(scope.team_member_ids))
    elif not scope.is_admin:
        query = query.where(User.id == scope.user.id)
    return [UserRef.model_validate(u) for u in db.scalars(query)]


@router.get("/duplicates")
def check_duplicates(
    db: DbDep,
    scope: ScopeDep,
    mobile: Annotated[str | None, Query(max_length=30)] = None,
    email: Annotated[str | None, Query(max_length=254)] = None,
    exclude_id: uuid.UUID | None = None,
) -> list[DuplicateMatch]:
    """Live duplicate warning while a form is being filled in (spec section 4.1)."""
    return find_duplicates(
        db, scope, clean_mobile(mobile or None), clean_email(email or None), exclude_id
    )
