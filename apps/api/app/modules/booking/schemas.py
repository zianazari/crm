import re
import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.booking.models import BookingStatus
from app.modules.crm.schemas import UserRef
from app.modules.messaging.models import Channel

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def parse_hhmm(value: str) -> time:
    hours, minutes = (int(x) for x in value.split(":"))
    return time(hours, minutes)


class RuleIO(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0 = Saturday
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        if not _HHMM.match(value):
            raise ValueError("ساعت باید به شکل ۰۹:۳۰ باشد.")
        return value


class SettingsIn(BaseModel):
    buffer_before_minutes: int = Field(ge=0, le=240)
    buffer_after_minutes: int = Field(ge=0, le=240)
    min_notice_minutes: int = Field(ge=0, le=20160)
    horizon_days: int = Field(ge=1, le=180)
    change_deadline_hours: int = Field(ge=0, le=336)
    rules: list[RuleIO] = Field(max_length=50)


class MeetingTypeIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    duration_minutes: int = Field(ge=10, le=480)
    description: str | None = Field(default=None, max_length=500)


class MeetingTypeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    duration_minutes: int | None = Field(default=None, ge=10, le=480)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class MeetingTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    duration_minutes: int
    description: str | None
    is_active: bool


class ExceptionIn(BaseModel):
    start_date: date
    end_date: date
    reason: str = Field(min_length=2, max_length=200)
    # A holiday for everyone (admins only) rather than this person's leave.
    organization: bool = False


class ExceptionOut(BaseModel):
    id: uuid.UUID
    start_date: date
    end_date: date
    reason: str
    organization: bool


class SettingsOut(SettingsIn):
    user: UserRef
    timezone: str
    meeting_types: list[MeetingTypeOut]
    exceptions: list[ExceptionOut]


class Day(BaseModel):
    date: date
    slots: list[datetime]


class Slots(BaseModel):
    timezone: str
    duration_minutes: int
    days: list[Day]


class CustomerRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class BookingOut(BaseModel):
    id: uuid.UUID
    status: BookingStatus
    start_at: datetime
    end_at: datetime
    meeting_title: str
    user: UserRef
    customer: CustomerRef
    activity_id: uuid.UUID
    deal_id: uuid.UUID | None
    contact_channel: Channel
    created_at: datetime
    canceled_at: datetime | None
    cancel_reason: str | None
    canceled_by: UserRef | None  # None with a cancel time: the customer canceled
    rescheduled_to_id: uuid.UUID | None


class LinkIn(BaseModel):
    customer_id: uuid.UUID
    meeting_type_id: uuid.UUID
    deal_id: uuid.UUID | None = None
    expires_in_days: int = Field(default=14, ge=1, le=60)
    send: Channel | None = None  # also send it by SMS or email; otherwise only copy it


class LinkOut(BaseModel):
    id: uuid.UUID
    user: UserRef
    customer: CustomerRef
    meeting_type: MeetingTypeOut
    deal_id: uuid.UUID | None
    created_by: UserRef
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    sent_via: Channel | None
    state: str
    booking: BookingOut | None


class LinkCreated(BaseModel):
    link: LinkOut
    # Shown once: only a hash of the token is stored.
    url: str


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class StartIn(BaseModel):
    start_at: datetime
