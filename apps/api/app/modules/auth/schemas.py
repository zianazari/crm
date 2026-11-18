import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.sender import Channel
from app.modules.identity.models import Role


class OtpRequestIn(BaseModel):
    channel: Channel
    destination: str = Field(min_length=3, max_length=254)


class OtpRequestOut(BaseModel):
    challenge_id: str
    expires_in: int
    resend_after: int


class OtpVerifyIn(BaseModel):
    challenge_id: str = Field(min_length=10, max_length=64)
    code: str = Field(min_length=1, max_length=20)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    role: Role
    team_id: uuid.UUID | None
    mobile: str | None
    email: str | None
    # A rep in a finance team: activities and team queue only (spec section 5).
    finance_member: bool = False
    # Team queues this user may open (member, the team's manager, or admin).
    queue_team_ids: list[uuid.UUID] = []
