import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.deps import DbDep, require_csrf
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
from app.modules.crm.models import Customer, CustomerOrganization, Organization, customer_tags
from app.modules.crm.schemas import (
    AssignIn,
    CustomerCreate,
    CustomerLimited,
    CustomerOut,
    CustomerUpdate,
    CustomerView,
    DuplicateConflict,
    OrganizationLinkIn,
    Page,
)
from app.modules.sales.models import Deal, DealStatus

router = APIRouter(prefix="/customers", tags=["customers"], dependencies=[Depends(require_csrf)])

_CONFLICT: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"model": DuplicateConflict}
}


def view(scope: AccessScope, customer: Customer) -> CustomerOut | CustomerLimited:
    if scope.has_full_access(customer.owner_id):
        return CustomerOut.model_validate(customer)
    return CustomerLimited.model_validate(customer)


def load(db: Session, customer_id: uuid.UUID, *, for_update: bool = False) -> Customer:
    query = select(Customer).where(Customer.id == customer_id)
    if for_update:
        query = query.with_for_update(of=Customer)
    customer = db.scalar(query)
    if customer is None:
        raise NOT_FOUND
    return customer


def load_editable(db: Session, scope: AccessScope, customer_id: uuid.UUID) -> Customer:
    customer = load(db, customer_id)
    scope.require_full(customer.owner_id)
    if customer.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="پرونده بایگانی شده است.")
    return customer


@router.get("")
def list_customers(
    db: DbDep,
    scope: ScopeDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    owner_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    mine: bool = False,
    archived: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[CustomerView]:
    query = select(Customer).order_by(Customer.created_at.desc(), Customer.id)
    if archived:
        if not (scope.is_admin or scope.is_manager):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="دسترسی مجاز نیست.")
        query = query.where(
            Customer.archived_at.is_not(None), scope.full_access_filter(Customer.owner_id)
        )
    else:
        query = query.where(Customer.archived_at.is_(None))
    if q and q.strip():
        query = query.where(search_condition(Customer, q.strip()))
    if owner_id:
        query = query.where(Customer.owner_id == owner_id)
    if mine:
        query = query.where(Customer.owner_id == scope.user.id)
    # Not part of the limited view: only search records visible in full.
    if source_id:
        query = query.where(
            Customer.source_id == source_id, scope.full_access_filter(Customer.owner_id)
        )
    if tag_id:
        query = query.where(
            Customer.id.in_(
                select(customer_tags.c.customer_id).where(customer_tags.c.tag_id == tag_id)
            ),
            scope.full_access_filter(Customer.owner_id),
        )
    if organization_id:
        query = query.where(
            Customer.id.in_(
                select(CustomerOrganization.customer_id).where(
                    CustomerOrganization.organization_id == organization_id
                )
            ),
            scope.full_access_filter(Customer.owner_id),
        )
    start, end = day_bounds(created_from, created_to)
    if start:
        query = query.where(Customer.created_at >= start)
    if end:
        query = query.where(Customer.created_at < end)

    rows, total = paginate(db, query, page, page_size)
    return Page[CustomerView](
        items=[view(scope, row) for row in rows], total=total, page=page, page_size=page_size
    )


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=CustomerOut, responses=_CONFLICT
)
def create_customer(body: CustomerCreate, db: DbDep, scope: ScopeDep) -> CustomerOut | JSONResponse:
    mobile, email = clean_mobile(body.mobile), clean_email(body.email)
    phone = body.phone.strip() if body.phone and body.phone.strip() else None
    if not (mobile or email or phone):
        raise unprocessable("حداقل یکی از موبایل، تلفن یا ایمیل لازم است.")
    owner = resolve_owner(db, scope, body.owner_id)
    check_source(db, body.source_id)
    tags = resolve_tags(db, body.tag_ids)
    organization = _organization(db, body.organization_id)
    if not body.allow_duplicate and (matches := find_duplicates(db, scope, mobile, email)):
        return duplicate_response(matches)

    customer = Customer(
        full_name=body.full_name.strip(),
        mobile=mobile,
        email=email,
        phone=phone,
        preferred_channel=body.preferred_channel,
        description=body.description,
        source_id=body.source_id,
        owner_id=owner.id,
        owner=owner,
        created_by_id=scope.user.id,
        sms_consent=bool(body.sms_consent),
        email_consent=bool(body.email_consent),
        consent_updated_at=datetime.now(UTC) if (body.sms_consent or body.email_consent) else None,
        tags=tags,
    )
    if organization is not None:
        customer.organizations.append(
            CustomerOrganization(organization=organization, job_title=body.job_title)
        )
    db.add(customer)
    db.commit()
    return CustomerOut.model_validate(customer)


@router.get("/{customer_id}")
def get_customer(customer_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> CustomerView:
    customer = load(db, customer_id)
    if customer.archived_at is not None and not scope.can_manage(customer.owner_id):
        raise NOT_FOUND
    return view(scope, customer)


@router.patch("/{customer_id}", response_model=CustomerOut, responses=_CONFLICT)
def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdate,
    db: DbDep,
    scope: ScopeDep,
    allow_duplicate: bool = False,
) -> CustomerOut | JSONResponse:
    customer = load_editable(db, scope, customer_id)
    data = body.model_dump(exclude_unset=True)
    if "mobile" in data:
        data["mobile"] = clean_mobile(data["mobile"])
    if "email" in data:
        data["email"] = clean_email(data["email"])
    if "phone" in data:
        data["phone"] = data["phone"].strip() if data["phone"] and data["phone"].strip() else None
    new_mobile = data.get("mobile", customer.mobile)
    new_email = data.get("email", customer.email)
    if not (new_mobile or new_email or data.get("phone", customer.phone)):
        raise unprocessable("حداقل یکی از موبایل، تلفن یا ایمیل لازم است.")
    if (new_mobile, new_email) != (customer.mobile, customer.email) and not allow_duplicate:
        matches = find_duplicates(db, scope, new_mobile, new_email, exclude_id=customer.id)
        if matches:
            return duplicate_response(matches)
    if "source_id" in data:
        check_source(db, data["source_id"])
    if "tag_ids" in data:
        customer.tags = resolve_tags(db, data.pop("tag_ids") or [])
    if "full_name" in data and data["full_name"] is None:
        data.pop("full_name")
    for key in ("sms_consent", "email_consent"):
        if data.get(key) is None:
            data.pop(key, None)
        elif data[key] != getattr(customer, key):
            customer.consent_updated_at = datetime.now(UTC)
    for key, value in data.items():
        setattr(customer, key, value)
    db.commit()
    return CustomerOut.model_validate(customer)


@router.post("/{customer_id}/assign")
def assign_customer(
    customer_id: uuid.UUID, body: AssignIn, db: DbDep, scope: ScopeDep
) -> CustomerOut:
    customer = load(db, customer_id, for_update=True)
    change_owner(db, scope, customer, "customer", body.owner_id, body.reason)
    db.commit()
    return CustomerOut.model_validate(customer)


@router.post("/{customer_id}/archive")
def archive_customer(customer_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> CustomerOut:
    customer = load(db, customer_id, for_update=True)
    # Spec 5: a customer with open deals cannot be archived; close or move them first.
    open_deals = db.scalar(
        select(func.count())
        .select_from(Deal)
        .where(
            Deal.customer_id == customer.id,
            Deal.status == DealStatus.OPEN,
            Deal.archived_at.is_(None),
        )
    )
    if open_deals:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="این مشتری فروش باز دارد؛ ابتدا فروش‌ها را ببندید یا به مشتری دیگری منتقل کنید.",
        )
    archive(scope, customer)
    db.commit()
    return CustomerOut.model_validate(customer)


@router.post("/{customer_id}/restore")
def restore_customer(customer_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> CustomerOut:
    customer = load(db, customer_id, for_update=True)
    restore(scope, customer)
    db.commit()
    return CustomerOut.model_validate(customer)


@router.post("/{customer_id}/organizations")
def link_organization(
    customer_id: uuid.UUID, body: OrganizationLinkIn, db: DbDep, scope: ScopeDep
) -> CustomerOut:
    customer = load_editable(db, scope, customer_id)
    organization = _organization(db, body.organization_id)
    if organization is None:
        raise unprocessable("سازمان انتخاب‌شده معتبر نیست.")
    link = next((x for x in customer.organizations if x.organization_id == organization.id), None)
    if link is None:
        customer.organizations.append(
            CustomerOrganization(organization=organization, job_title=body.job_title)
        )
    else:
        link.job_title = body.job_title
    db.commit()
    db.refresh(customer)
    return CustomerOut.model_validate(customer)


@router.delete("/{customer_id}/organizations/{organization_id}")
def unlink_organization(
    customer_id: uuid.UUID, organization_id: uuid.UUID, db: DbDep, scope: ScopeDep
) -> CustomerOut:
    customer = load_editable(db, scope, customer_id)
    customer.organizations = [
        x for x in customer.organizations if x.organization_id != organization_id
    ]
    db.commit()
    return CustomerOut.model_validate(customer)


def _organization(db: Session, organization_id: uuid.UUID | None) -> Organization | None:
    if organization_id is None:
        return None
    organization = db.get(Organization, organization_id)
    if organization is None or organization.archived_at is not None:
        raise unprocessable("سازمان انتخاب‌شده معتبر نیست.")
    return organization
