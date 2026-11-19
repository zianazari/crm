"""Queueing and sending messages (spec 7 "reliable queue and delivery", 8 OTP).

``enqueue`` writes the message and its outbox row in the caller's transaction.
``process`` is what the worker runs for one queue delivery; it is safe to run more
than once for the same message (deliveries can repeat).
"""

import enum
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.modules.messaging.models import (
    FINAL_STATUSES,
    Channel,
    DeliveryEvent,
    MessageStatus,
    OutboundMessage,
    OutboxEvent,
    Purpose,
)
from app.modules.messaging.providers import (
    AmbiguousError,
    PermanentError,
    Providers,
    TemporaryError,
)

logger = logging.getLogger("crm.messaging")

OTP_QUEUE = "messages.otp"
SEND_QUEUE = "messages.send"


def namespaced(name: str) -> str:
    namespace = get_settings().queue_namespace
    return f"{namespace}.{name}" if namespace else name


def queue_for(purpose: Purpose) -> str:
    """OTP has its own queue so a large send never delays a login (spec 7)."""
    return namespaced(OTP_QUEUE if purpose is Purpose.OTP else SEND_QUEUE)


def otp_code_key(message_id: uuid.UUID) -> str:
    return f"otp:outbox:{message_id}"


def enqueue(
    db: Session,
    channel: Channel,
    purpose: Purpose,
    recipient: str,
    *,
    subject: str | None = None,
    body: str | None = None,
    user_id: uuid.UUID | None = None,
    challenge_id: str | None = None,
    expires_at: datetime | None = None,
) -> OutboundMessage:
    message = OutboundMessage(
        channel=channel,
        purpose=purpose,
        recipient=recipient,
        subject=subject,
        body=body,
        user_id=user_id,
        challenge_id=challenge_id,
        expires_at=expires_at,
    )
    db.add(message)
    db.flush()
    db.add(OutboxEvent(routing_key=queue_for(purpose), payload={"message_id": str(message.id)}))
    return message


# -- worker step -----------------------------------------------------------------


class Outcome(enum.Enum):
    DONE = "done"  # acknowledge; nothing more to do
    RETRY = "retry"  # acknowledge and re-queue after ``delay`` seconds
    DEAD = "dead"  # acknowledge and park in the dead-letter queue for inspection


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    delay: int = 0


def backoff(purpose: Purpose, attempts: int) -> int:
    # An OTP is only useful for two minutes; everything else can wait longer.
    if purpose is Purpose.OTP:
        return min(3 * attempts, 20)
    return min(5 * (1 << max(attempts - 1, 0)), 300)


def _otp_text(code: str) -> str:
    return f"کد ورود شما به CRM: {code}\nاین کد تا ۲ دقیقه معتبر است. آن را به کسی ندهید."


def process(
    db: Session, redis: Redis, providers: Providers, settings: Settings, message_id: uuid.UUID
) -> Result:
    message = db.scalar(
        select(OutboundMessage).where(OutboundMessage.id == message_id).with_for_update()
    )
    if message is None or message.status in FINAL_STATUSES:
        return Result(Outcome.DONE)  # repeated delivery of a finished message
    if message.status is MessageStatus.SENDING:
        # A previous worker stopped mid-send: the provider may already have it.
        _finish(db, message, MessageStatus.UNKNOWN, "worker stopped during send")
        return Result(Outcome.DONE)

    subject, text = message.subject, message.body
    if message.purpose is Purpose.OTP:
        code = redis.get(otp_code_key(message.id))
        # A newer code deletes the older challenge, and a used or expired one is gone.
        current = bool(redis.exists(f"otp:challenge:{message.challenge_id}"))
        now = datetime.now(UTC)
        if (
            not code
            or not current
            or (message.expires_at is not None and now >= message.expires_at)
        ):
            # Never deliver a code that can no longer be used (spec 8.4).
            _finish(db, message, MessageStatus.EXPIRED, "challenge ended before sending")
            return Result(Outcome.DONE)
        text, subject = _otp_text(str(code)), "کد ورود CRM"
    if message.purpose is Purpose.MARKETING and _suppressed(db, message):
        # Unsubscribed after it was queued: the last check, right before sending.
        _finish(db, message, MessageStatus.CANCELED, "در فهرست عدم ارسال است.")
        return Result(Outcome.DONE)

    message.status = MessageStatus.SENDING
    message.attempts += 1
    db.commit()  # visible before calling out, so a crash leaves "sending" behind

    try:
        if message.channel is Channel.SMS:
            accepted = providers.sms.send(message.recipient, text or "", str(message.id))
        else:
            accepted = providers.email.send(
                message.recipient, subject or "", text or "", str(message.id)
            )
    except TemporaryError as exc:
        if message.attempts >= settings.message_max_attempts:
            _finish(db, message, MessageStatus.FAILED, f"attempts exhausted: {exc}")
            return Result(Outcome.DEAD)
        message.status = MessageStatus.QUEUED
        message.last_error = str(exc)[:500]
        db.commit()
        return Result(Outcome.RETRY, backoff(message.purpose, message.attempts))
    except PermanentError as exc:
        _finish(db, message, MessageStatus.FAILED, str(exc))
        return Result(Outcome.DEAD)
    except AmbiguousError as exc:
        _finish(db, message, MessageStatus.UNKNOWN, str(exc))
        return Result(Outcome.DONE)

    message.status = MessageStatus.ACCEPTED
    message.provider_message_id = accepted.provider_message_id
    message.sent_at = datetime.now(UTC)
    message.last_error = None
    db.commit()
    if message.purpose is Purpose.OTP:
        redis.delete(otp_code_key(message.id))
    return Result(Outcome.DONE)


def _suppressed(db: Session, message: OutboundMessage) -> bool:
    from app.modules.campaigns.models import Suppression  # campaigns builds on messaging

    return (
        db.scalar(
            select(Suppression.id).where(
                Suppression.channel == message.channel,
                Suppression.address == message.recipient,
            )
        )
        is not None
    )


def _finish(db: Session, message: OutboundMessage, status: MessageStatus, error: str) -> None:
    message.status = status
    message.last_error = error[:500]
    db.commit()
    if message.purpose is Purpose.OTP:
        logger.info("OTP message %s ended as %s", message.id, status.value)


# -- delivery reports ------------------------------------------------------------


class InvalidSignatureError(Exception):
    pass


def verify_signature(secret: str, body: bytes, signature: str) -> None:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise InvalidSignatureError


_REPORTED = {"delivered": MessageStatus.DELIVERED, "failed": MessageStatus.FAILED}
# A report can only move a message forward; late or repeated reports never undo it.
_REPORTABLE_FROM = {MessageStatus.SENDING, MessageStatus.ACCEPTED, MessageStatus.UNKNOWN}


def apply_delivery_report(db: Session, payload: dict[str, Any]) -> bool:
    """Returns True when the report changed something."""
    event_id = str(payload.get("event_id") or "")
    provider_id = str(payload.get("message_id") or "")
    status = _REPORTED.get(str(payload.get("status")))
    if not event_id or not provider_id or status is None:
        return False
    message = db.scalar(
        select(OutboundMessage)
        .where(OutboundMessage.provider_message_id == provider_id)
        .with_for_update()
    )
    if message is None:
        return False
    db.add(
        DeliveryEvent(
            message_id=message.id, provider_event_id=event_id, status=status.value, raw=payload
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()  # the same report again
        return False
    changed = message.status in _REPORTABLE_FROM
    if changed:
        message.status = status
        if status is MessageStatus.DELIVERED:
            message.delivered_at = datetime.now(UTC)
        else:
            message.last_error = "provider reported delivery failure"
    db.commit()
    return changed


def parse_json(body: bytes) -> dict[str, Any]:
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("expected an object")
    return data


def otp_expiry(ttl_seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=ttl_seconds)
