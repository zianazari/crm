import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crm.schemas import Ref, UserRef
from app.modules.sales.models import DealStatus, PaymentKind

Amount = Annotated[int, Field(ge=0, le=10**15)]
Version = Annotated[int, Field(ge=1)]


class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool


class StageIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    sort_order: int = 0


class StageDeactivateIn(BaseModel):
    """Open deals in the stage are moved here first (spec 4.3)."""

    move_to_stage_id: uuid.UUID | None = None


class CustomerName(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class DealLimited(BaseModel):
    """What anyone may see of a deal they do not own: name, title, stage/result, owner,
    last activity (spec section 0, decision 4)."""

    model_config = ConfigDict(from_attributes=True)

    access: Literal["limited"] = "limited"
    id: uuid.UUID
    title: str
    customer: CustomerName
    stage: Ref
    status: DealStatus
    owner: UserRef
    last_activity_at: datetime | None
    created_at: datetime
    closed_at: datetime | None


class DealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access: Literal["full"] = "full"
    id: uuid.UUID
    title: str
    customer: CustomerName
    stage: Ref
    status: DealStatus
    owner: UserRef
    last_activity_at: datetime | None
    created_at: datetime
    closed_at: datetime | None
    updated_at: datetime
    version: int
    description: str | None
    organization: Ref | None
    amount: int | None
    currency: str
    expected_close_date: date | None
    contract_amount: int | None
    contract_date: date | None
    lost_reason: str | None
    archived_at: datetime | None
    # Payments, net of refunds and voided entries.
    paid_amount: int = 0
    # Won deals only: contract amount minus net payments (spec section 0, decision 2).
    outstanding_amount: int | None = None


DealView = Annotated[DealOut | DealLimited, Field(discriminator="access")]


class DealCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    customer_id: uuid.UUID
    organization_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    amount: Amount | None = None
    expected_close_date: date | None = None
    description: str | None = Field(default=None, max_length=5000)
    owner_id: uuid.UUID | None = None


class DealUpdate(BaseModel):
    version: Version
    title: str | None = Field(default=None, min_length=2, max_length=200)
    organization_id: uuid.UUID | None = None
    amount: Amount | None = None
    expected_close_date: date | None = None
    description: str | None = Field(default=None, max_length=5000)


class MoveIn(BaseModel):
    stage_id: uuid.UUID
    version: Version


class WinIn(BaseModel):
    contract_amount: Amount
    contract_date: date
    version: Version


class LoseIn(BaseModel):
    lost_reason: str = Field(min_length=2, max_length=300)
    version: Version


class ReopenIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)
    stage_id: uuid.UUID | None = None
    version: Version


class AssignDealIn(BaseModel):
    owner_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=300)


class BoardColumn(BaseModel):
    stage: StageOut
    count: int
    # Sum of estimated amounts of deals the user can see in full; matches the cards.
    total_amount: int
    deals: list[DealView]
    truncated: bool


class BoardOutcome(BaseModel):
    closed_from: date
    won_count: int
    won_total: int
    lost_count: int
    deals: list[DealView]
    truncated: bool


class Board(BaseModel):
    columns: list[BoardColumn]
    outcome: BoardOutcome


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_stage: Ref | None
    to_stage: Ref
    from_status: DealStatus | None
    to_status: DealStatus
    changed_by: UserRef
    reason: str | None
    changed_at: datetime


class PaymentIn(BaseModel):
    kind: PaymentKind = PaymentKind.PAYMENT
    amount: Annotated[int, Field(gt=0, le=10**15)]
    paid_on: date
    reference: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


class VoidIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: PaymentKind
    amount: int
    currency: str
    paid_on: date
    reference: str | None
    note: str | None
    recorded_by: UserRef
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None
