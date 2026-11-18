import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.deps import DbDep, require_csrf
from app.modules.automation.events import emit
from app.modules.crm.access import AccessScope
from app.modules.crm.common import (
    NOT_FOUND,
    ScopeDep,
    archive,
    change_owner,
    check_source,
    clean_email,
    clean_mobile,
    day_bounds,
    duplicate_response,
    find_duplicates,
    paginate,
    resolve_owner,
    resolve_tags,
    restore,
    search_condition,
    unprocessable,
)
from app.modules.crm.models import (
    Customer,
    CustomerOrganization,
    Lead,
    LeadStatus,
    Organization,
    lead_tags,
)
from app.modules.crm.schemas import (
    AssignIn,
    ConvertIn,
    ConvertOut,
    DuplicateConflict,
    LeadCreate,
    LeadLimited,
    LeadOut,
    LeadUpdate,
    LeadView,
    Page,
)

router = APIRouter(prefix="/leads", tags=["leads"], dependencies=[Depends(require_csrf)])

_CONFLICT: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"model": DuplicateConflict}
}


def view(scope: AccessScope, lead: Lead) -> LeadOut | LeadLimited:
    if scope.has_full_access(lead.owner_id):
        return LeadOut.model_validate(lead)
    return LeadLimited.model_validate(lead)


def load(db: Session, lead_id: uuid.UUID, *, for_update: bool = False) -> Lead:
    query = select(Lead).where(Lead.id == lead_id)
    if for_update:
        query = query.with_for_update(of=Lead)
    lead = db.scalar(query)
    if lead is None:
        raise NOT_FOUND
    return lead


def load_full(db: Session, scope: AccessScope, lead_id: uuid.UUID) -> Lead:
    lead = load(db, lead_id)
    scope.require_full(lead.owner_id)
    return lead


@router.get("")
def list_leads(
    db: DbDep,
    scope: ScopeDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[LeadStatus | None, Query(alias="status")] = None,
    owner_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    mine: bool = False,
    archived: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[LeadView]:
    query = select(Lead).order_by(Lead.created_at.desc(), Lead.id)
    if archived:
        # Archived records are a management view.
        if not (scope.is_admin or scope.is_manager):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="دسترسی مجاز نیست.")
        query = query.where(Lead.archived_at.is_not(None), scope.full_access_filter(Lead.owner_id))
    else:
        query = query.where(Lead.archived_at.is_(None))
    if q and q.strip():
        query = query.where(search_condition(Lead, q.strip()))
    if status_:
        query = query.where(Lead.status == status_)
    if owner_id:
        query = query.where(Lead.owner_id == owner_id)
    if mine:
        query = query.where(Lead.owner_id == scope.user.id)
    # Source and tags are not part of the limited view, so filtering on them only
    # searches records the user may see in full.
    if source_id:
        query = query.where(Lead.source_id == source_id, scope.full_access_filter(Lead.owner_id))
    if tag_id:
        query = query.where(
            Lead.id.in_(select(lead_tags.c.lead_id).where(lead_tags.c.tag_id == tag_id)),
            scope.full_access_filter(Lead.owner_id),
        )
    start, end = day_bounds(created_from, created_to)
    if start:
        query = query.where(Lead.created_at >= start)
    if end:
        query = query.where(Lead.created_at < end)

    rows, total = paginate(db, query, page, page_size)
    return Page[LeadView](
        items=[view(scope, row) for row in rows], total=total, page=page, page_size=page_size
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=LeadOut, responses=_CONFLICT)
def create_lead(body: LeadCreate, db: DbDep, scope: ScopeDep) -> LeadOut | JSONResponse:
    mobile, email = clean_mobile(body.mobile), clean_email(body.email)
    if not mobile and not email:
        raise unprocessable("موبایل یا ایمیل لازم است.")
    owner = resolve_owner(db, scope, body.owner_id)
    check_source(db, body.source_id)
    tags = resolve_tags(db, body.tag_ids)
    if not body.allow_duplicate and (matches := find_duplicates(db, scope, mobile, email)):
        return duplicate_response(matches)

    lead = Lead(
        full_name=body.full_name.strip(),
        mobile=mobile,
        email=email,
        company_name=body.company_name,
        description=body.description,
        source_id=body.source_id,
        acquisition=body.acquisition,
        owner_id=owner.id,
        owner=owner,
        created_by_id=scope.user.id,
        sms_consent=bool(body.sms_consent),
        email_consent=bool(body.email_consent),
        consent_updated_at=datetime.now(UTC) if (body.sms_consent or body.email_consent) else None,
        tags=tags,
    )
    db.add(lead)
    db.flush()
    emit(db, "lead.created", "lead", lead.id)
    db.commit()
    return LeadOut.model_validate(lead)


@router.get("/{lead_id}")
def get_lead(lead_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> LeadView:
    lead = load(db, lead_id)
    if lead.archived_at is not None and not scope.can_manage(lead.owner_id):
        raise NOT_FOUND
    return view(scope, lead)


@router.patch("/{lead_id}", response_model=LeadOut, responses=_CONFLICT)
def update_lead(
    lead_id: uuid.UUID, body: LeadUpdate, db: DbDep, scope: ScopeDep, allow_duplicate: bool = False
) -> LeadOut | JSONResponse:
    lead = load_full(db, scope, lead_id)
    if lead.status is LeadStatus.CONVERTED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="سرنخ تبدیل‌شده قابل ویرایش نیست.")
    if lead.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="پرونده بایگانی شده است.")
    data = body.model_dump(exclude_unset=True)

    if "mobile" in data:
        data["mobile"] = clean_mobile(data["mobile"])
    if "email" in data:
        data["email"] = clean_email(data["email"])
    new_mobile = data.get("mobile", lead.mobile)
    new_email = data.get("email", lead.email)
    if not new_mobile and not new_email:
        raise unprocessable("موبایل یا ایمیل لازم است.")
    contact_changed = (new_mobile, new_email) != (lead.mobile, lead.email)
    if contact_changed and not allow_duplicate:
        matches = find_duplicates(db, scope, new_mobile, new_email, exclude_id=lead.id)
        if matches:
            return duplicate_response(matches)

    if "source_id" in data:
        check_source(db, data["source_id"])
    if "tag_ids" in data:
        lead.tags = resolve_tags(db, data.pop("tag_ids") or [])
    if "full_name" in data and data["full_name"] is None:
        data.pop("full_name")

    new_status = data.get("status", lead.status)
    reason = data.get("disqualify_reason", lead.disqualify_reason)
    if new_status is LeadStatus.DISQUALIFIED:
        if not (reason and reason.strip()):
            raise unprocessable("برای نامناسب‌بودن سرنخ، دلیل لازم است.")
    else:
        data["disqualify_reason"] = None

    for key in ("sms_consent", "email_consent"):
        if data.get(key) is None:
            data.pop(key, None)
        elif data[key] != getattr(lead, key):
            lead.consent_updated_at = datetime.now(UTC)
    for key, value in data.items():
        setattr(lead, key, value)
    db.commit()
    return LeadOut.model_validate(lead)


@router.post("/{lead_id}/assign")
def assign_lead(lead_id: uuid.UUID, body: AssignIn, db: DbDep, scope: ScopeDep) -> LeadOut:
    lead = load(db, lead_id, for_update=True)
    change_owner(db, scope, lead, "lead", body.owner_id, body.reason)
    db.commit()
    return LeadOut.model_validate(lead)


@router.post("/{lead_id}/archive")
def archive_lead(lead_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> LeadOut:
    lead = load(db, lead_id, for_update=True)
    archive(scope, lead)
    db.commit()
    return LeadOut.model_validate(lead)


@router.post("/{lead_id}/restore")
def restore_lead(lead_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> LeadOut:
    lead = load(db, lead_id, for_update=True)
    restore(scope, lead)
    db.commit()
    return LeadOut.model_validate(lead)


@router.post("/{lead_id}/convert", response_model=ConvertOut, responses=_CONFLICT)
def convert_lead(
    lead_id: uuid.UUID, body: ConvertIn, db: DbDep, scope: ScopeDep, allow_duplicate: bool = False
) -> ConvertOut | JSONResponse:
    """Atomic and idempotent: the lead row is locked, and converting an already converted
    lead returns the original result instead of creating another customer."""
    lead = load(db, lead_id, for_update=True)
    scope.require_full(lead.owner_id)
    if lead.status is LeadStatus.CONVERTED and lead.converted_customer_id:
        return ConvertOut(
            lead_id=lead.id,
            customer_id=lead.converted_customer_id,
            created_customer=False,
            organization_id=None,
        )
    if lead.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="پرونده بایگانی شده است.")
    if lead.status is LeadStatus.DISQUALIFIED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="سرنخ نامناسب قابل تبدیل نیست.")

    created = body.customer_id is None
    if body.customer_id is not None:
        customer = db.get(Customer, body.customer_id)
        if customer is None or customer.archived_at is not None:
            raise NOT_FOUND
        # Linking adds this lead's history to that file, so it needs full access to it.
        scope.require_full(customer.owner_id)
    else:
        if not allow_duplicate:
            matches = [
                m
                for m in find_duplicates(db, scope, lead.mobile, lead.email)
                if m.kind == "customer"
            ]
            if matches:
                return duplicate_response(matches)
        customer = Customer(
            full_name=lead.full_name,
            mobile=lead.mobile,
            email=lead.email,
            description=lead.description,
            source_id=lead.source_id,
            owner_id=lead.owner_id,
            created_by_id=scope.user.id,
            tags=list(lead.tags),
        )
        db.add(customer)
        db.flush()

    organization = _conversion_organization(db, scope, lead, body, created)
    if organization is not None and all(
        link.organization_id != organization.id for link in customer.organizations
    ):
        customer.organizations.append(
            CustomerOrganization(organization=organization, job_title=body.job_title)
        )

    lead.status = LeadStatus.CONVERTED
    lead.converted_customer_id = customer.id
    lead.converted_at = datetime.now(UTC)
    lead.converted_by_id = scope.user.id
    db.commit()
    return ConvertOut(
        lead_id=lead.id,
        customer_id=customer.id,
        created_customer=created,
        organization_id=organization.id if organization else None,
    )


def _conversion_organization(
    db: Session, scope: AccessScope, lead: Lead, body: ConvertIn, created: bool
) -> Organization | None:
    if body.organization_id is not None:
        organization = db.get(Organization, body.organization_id)
        if organization is None or organization.archived_at is not None:
            raise unprocessable("سازمان انتخاب‌شده معتبر نیست.")
        return organization
    if not (created and body.create_organization and lead.company_name):
        return None
    name = lead.company_name.strip()
    existing = db.scalar(
        select(Organization)
        .where(func.lower(Organization.name) == name.lower(), Organization.archived_at.is_(None))
        .limit(1)
    )
    if existing is not None:
        return existing
    organization = Organization(name=name, created_by_id=scope.user.id)
    db.add(organization)
    return organization
