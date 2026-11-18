import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.modules.auth.deps import DbDep, require_csrf
from app.modules.crm.common import NOT_FOUND, ScopeDep, paginate, require_sales_access
from app.modules.crm.customers import view as customer_view
from app.modules.crm.models import Organization
from app.modules.crm.schemas import (
    OrganizationDetail,
    OrganizationIn,
    OrganizationMemberOut,
    OrganizationOut,
    Page,
)

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)


@router.get("")
def list_organizations(
    db: DbDep,
    _: ScopeDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[OrganizationOut]:
    query = (
        select(Organization)
        .where(Organization.archived_at.is_(None))
        .order_by(Organization.name, Organization.id)
    )
    if q and q.strip():
        query = query.where(Organization.name.icontains(q.strip(), autoescape=True))
    rows, total = paginate(db, query, page, page_size)
    return Page[OrganizationOut](
        items=[OrganizationOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_organization(body: OrganizationIn, db: DbDep, scope: ScopeDep) -> OrganizationOut:
    organization = Organization(
        name=body.name.strip(),
        phone=body.phone,
        website=body.website,
        created_by_id=scope.user.id,
    )
    db.add(organization)
    db.commit()
    return OrganizationOut.model_validate(organization)


@router.get("/{organization_id}")
def get_organization(organization_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> OrganizationDetail:
    organization = db.get(Organization, organization_id)
    if organization is None or organization.archived_at is not None:
        raise NOT_FOUND
    members = [
        OrganizationMemberOut(customer=customer_view(scope, m.customer), job_title=m.job_title)
        for m in organization.members
        if m.customer.archived_at is None
    ]
    return OrganizationDetail(
        **OrganizationOut.model_validate(organization).model_dump(), members=members
    )


@router.patch("/{organization_id}")
def update_organization(
    organization_id: uuid.UUID, body: OrganizationIn, db: DbDep, scope: ScopeDep
) -> OrganizationOut:
    # Shared reference data: editable by its creator, managers and admins.
    organization = db.get(Organization, organization_id)
    if organization is None or organization.archived_at is not None:
        raise NOT_FOUND
    if not (scope.is_admin or scope.is_manager or organization.created_by_id == scope.user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="ویرایش این سازمان مجاز نیست.")
    organization.name = body.name.strip()
    organization.phone = body.phone
    organization.website = body.website
    db.commit()
    return OrganizationOut.model_validate(organization)
