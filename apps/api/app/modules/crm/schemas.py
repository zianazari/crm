import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.crm.models import ContactChannel, LeadStatus

Name = Annotated[str, Field(min_length=2, max_length=160)]


def _strip(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class Ref(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class UserRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    # Photo version for /users/{id}/avatar?v=…; none means show the initial.
    avatar_version: int | None = None


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


# -- reference data -------------------------------------------------------


class LeadSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_active: bool
    sort_order: int


class LeadSourceIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    is_active: bool = True
    sort_order: int = 0


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)


# -- contact fields shared by create/update -------------------------------


class ContactFields(BaseModel):
    mobile: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=254)

    _strip_contact = field_validator("mobile", "email", mode="before")(_strip)


# -- leads ------------------------------------------------------------------


class LeadCreate(ContactFields):
    sms_consent: bool | None = None
    email_consent: bool | None = None
    full_name: Name
    company_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    source_id: uuid.UUID | None = None
    acquisition: dict[str, Any] | None = None
    owner_id: uuid.UUID | None = None  # defaults to the creator
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    allow_duplicate: bool = False


class LeadUpdate(ContactFields):
    sms_consent: bool | None = None
    email_consent: bool | None = None
    full_name: Name | None = None
    company_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    source_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    status: (
        Literal[LeadStatus.NEW, LeadStatus.WORKING, LeadStatus.QUALIFIED, LeadStatus.DISQUALIFIED]
        | None
    ) = None
    disqualify_reason: str | None = Field(default=None, max_length=300)
    last_contacted_at: datetime | None = None


class LeadLimited(BaseModel):
    """What anyone may see of a lead they do not own."""

    model_config = ConfigDict(from_attributes=True)

    access: Literal["limited"] = "limited"
    id: uuid.UUID
    full_name: str
    status: LeadStatus
    owner: UserRef
    last_contacted_at: datetime | None
    created_at: datetime


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access: Literal["full"] = "full"
    id: uuid.UUID
    full_name: str
    status: LeadStatus
    owner: UserRef
    last_contacted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    mobile: str | None
    email: str | None
    company_name: str | None
    description: str | None
    source: Ref | None
    acquisition: dict[str, Any] | None
    tags: list[Ref]
    disqualify_reason: str | None
    converted_customer_id: uuid.UUID | None
    converted_at: datetime | None
    archived_at: datetime | None
    sms_consent: bool
    email_consent: bool
    consent_updated_at: datetime | None


LeadView = Annotated[LeadOut | LeadLimited, Field(discriminator="access")]


class AssignIn(BaseModel):
    owner_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=300)


class ConvertIn(BaseModel):
    """Convert to a new customer, or attach to an existing one (no duplicate is created)."""

    customer_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    # Create an organization from the lead's company name when no id is given.
    create_organization: bool = True
    job_title: str | None = Field(default=None, max_length=120)


class ConvertOut(BaseModel):
    lead_id: uuid.UUID
    customer_id: uuid.UUID
    created_customer: bool
    organization_id: uuid.UUID | None


# -- customers -------------------------------------------------------------


class CustomerOrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization: Ref
    job_title: str | None


class CustomerCreate(ContactFields):
    sms_consent: bool | None = None
    email_consent: bool | None = None
    full_name: Name
    phone: str | None = Field(default=None, max_length=30)
    preferred_channel: ContactChannel | None = None
    description: str | None = Field(default=None, max_length=5000)
    source_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    organization_id: uuid.UUID | None = None
    job_title: str | None = Field(default=None, max_length=120)
    allow_duplicate: bool = False


class CustomerUpdate(ContactFields):
    sms_consent: bool | None = None
    email_consent: bool | None = None
    full_name: Name | None = None
    phone: str | None = Field(default=None, max_length=30)
    preferred_channel: ContactChannel | None = None
    description: str | None = Field(default=None, max_length=5000)
    source_id: uuid.UUID | None = None
    tag_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


class CustomerLimited(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access: Literal["limited"] = "limited"
    id: uuid.UUID
    full_name: str
    owner: UserRef
    last_activity_at: datetime | None
    created_at: datetime


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access: Literal["full"] = "full"
    id: uuid.UUID
    full_name: str
    owner: UserRef
    last_activity_at: datetime | None
    created_at: datetime
    updated_at: datetime
    mobile: str | None
    phone: str | None
    email: str | None
    preferred_channel: ContactChannel | None
    description: str | None
    source: Ref | None
    tags: list[Ref]
    organizations: list[CustomerOrganizationOut]
    archived_at: datetime | None
    sms_consent: bool
    email_consent: bool
    consent_updated_at: datetime | None


CustomerView = Annotated[CustomerOut | CustomerLimited, Field(discriminator="access")]


class OrganizationLinkIn(BaseModel):
    organization_id: uuid.UUID
    job_title: str | None = Field(default=None, max_length=120)


# -- organizations ---------------------------------------------------------


class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    website: str | None = Field(default=None, max_length=200)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str | None
    website: str | None
    created_at: datetime


class OrganizationMemberOut(BaseModel):
    customer: CustomerView
    job_title: str | None


class OrganizationDetail(OrganizationOut):
    members: list[OrganizationMemberOut]


# -- duplicates ------------------------------------------------------------


class DuplicateMatch(BaseModel):
    kind: Literal["customer", "lead"]
    id: uuid.UUID
    full_name: str
    owner: UserRef
    matched_on: list[Literal["mobile", "email"]]
    access: Literal["full", "limited"]


class DuplicateConflict(BaseModel):
    detail: str
    matches: list[DuplicateMatch]
