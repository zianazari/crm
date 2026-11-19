import enum
import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.messaging.models import Channel as MessageChannel
from app.modules.messaging.models import Purpose
from app.modules.messaging.service import enqueue, otp_code_key, otp_expiry

logger = logging.getLogger("crm.auth.otp")


class Channel(enum.StrEnum):
    SMS = "sms"
    EMAIL = "email"


@dataclass(frozen=True)
class OtpContext:
    """Lets the worker check the challenge is still current before it sends."""

    challenge_id: str
    user_id: uuid.UUID | None  # staff only; portal identities are not users
    ttl_seconds: int


class OtpSender(Protocol):
    def send(self, channel: Channel, destination: str, code: str, context: OtpContext) -> None: ...


class DevConsoleOtpSender:
    """Development only (spec section 0, decision 8): prints the code to the API log.

    Never used in test, staging or production, where raw codes must not be logged.
    """

    def send(self, channel: Channel, destination: str, code: str, context: OtpContext) -> None:
        logger.warning("DEV OTP via %s to %s: %s", channel.value, destination, code)


class QueuedOtpSender:
    """Sends through the outbox, RabbitMQ and the worker (spec 8.4). The raw code is kept
    only in Redis, expiring with the challenge; the database never stores it."""

    def __init__(self, db: Session, redis: Redis) -> None:
        self.db = db
        self.redis = redis

    def send(self, channel: Channel, destination: str, code: str, context: OtpContext) -> None:
        message = enqueue(
            self.db,
            MessageChannel(channel.value),
            Purpose.OTP,
            destination,
            user_id=context.user_id,
            challenge_id=context.challenge_id,
            expires_at=otp_expiry(context.ttl_seconds),
        )
        self.redis.set(otp_code_key(message.id), code, ex=context.ttl_seconds)
        self.db.commit()


class SenderNotConfiguredError(RuntimeError):
    pass


def build_otp_sender(settings: Settings, db: Session, redis: Redis) -> OtpSender:
    if settings.messaging_mode == "queue":
        return QueuedOtpSender(db, redis)
    if settings.is_development:
        return DevConsoleOtpSender()
    # Outside development, codes are only ever delivered through the queue.
    raise SenderNotConfiguredError("OTP delivery requires CRM_MESSAGING_MODE=queue")
