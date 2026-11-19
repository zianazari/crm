import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.activities.models import ActivityStatus, ActivityType, Priority
from app.modules.crm.schemas import UserRef

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
Version = Annotated[int, Field(ge=1)]


class LinkRef(BaseModel):
    """A linked lead, customer or deal: its id and display name."""

    id: uuid.UUID
    name: str

    @model_validator(mode="before")
    @classmethod
    def _from_record(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return value
        name = getattr(value, "full_name", None) or getattr(value, "title", None)
        return {"id": value.id, "name": name}


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: ActivityType
    title: str
    description: str | None
    owner: UserRef
    created_by: UserRef
    due_date: date
    start_at: datetime | None
    duration_minutes: int | None
    priority: Priority
    reminder_minutes: int | None
    status: ActivityStatus
    outcome: str | None
    cancel_reason: str | None
    completed_at: datetime | None
    completed_by: UserRef | None
    created_at: datetime
    version: int
    lead: LinkRef | None = None
    customer: LinkRef | None = None
    deal: LinkRef | None = None
    # The team-queue task this activity came from, if any.
    team_task_id: uuid.UUID | None = None
    overdue: bool = False


class ActivityBrief(BaseModel):
    """Next action shown on a sales board card."""

    id: uuid.UUID
    type: ActivityType
    title: str
    due_date: date
    start_at: datetime | None
    overdue: bool


class Schedule(BaseModel):
    due_date: date
    # Local time in the organization's time zone; omitted for date-only activities.
    start_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    duration_minutes: int | None = Field(default=None, gt=0, le=24 * 60)


class ActivityCreate(Schedule):
    type: ActivityType
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    owner_id: uuid.UUID | None = None
    priority: Priority = Priority.NORMAL
    reminder_minutes: int | None = Field(default=None, ge=0, le=7 * 24 * 60)
    lead_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


class ActivityUpdate(BaseModel):
    version: Version
    type: ActivityType | None = None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    owner_id: uuid.UUID | None = None
    priority: Priority | None = None
    reminder_minutes: int | None = Field(default=None, ge=0, le=7 * 24 * 60)
    due_date: date | None = None
    start_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    duration_minutes: int | None = Field(default=None, gt=0, le=24 * 60)


class CompleteIn(BaseModel):
    outcome: str = Field(min_length=1, max_length=5000)
    version: Version

    @field_validator("outcome")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("outcome is required")
        return value.strip()


class PostponeIn(Schedule):
    version: Version
    reason: str | None = Field(default=None, max_length=300)


class CancelIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)
    version: Version


class StartIn(BaseModel):
    version: Version


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    details: dict[str, Any] | None
    actor: UserRef
    at: datetime


class Overlap(BaseModel):
    first: uuid.UUID
    second: uuid.UUID


class Workload(BaseModel):
    """Today's load for one person (spec 4.2)."""

    date: date
    owner: UserRef
    open_count: int
    overdue_count: int
    timed_minutes: int
    overlaps: list[Overlap]


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    lead_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    author: UserRef
    created_at: datetime


TimelineKind = Literal["activity", "note", "stage", "payment", "message"]


class TimelineEntry(BaseModel):
    kind: TimelineKind
    id: uuid.UUID
    at: datetime
    actor: UserRef
    title: str
    body: str | None = None
    activity: ActivityOut | None = None
    deal: LinkRef | None = None
    # A template message sent from the record: its delivery status (queued, accepted…).
    message_status: str | None = None


class TimelinePage(BaseModel):
    items: list[TimelineEntry]
    has_more: bool
