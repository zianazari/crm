"""Outbox, queue worker, providers and delivery reports (spec 7, 8; criteria 10, 11)."""

import hashlib
import hmac
import json
import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta

import pika
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import Settings, get_settings
from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.modules.messaging import broker
from app.modules.messaging.models import (
    Channel,
    MessageStatus,
    OutboundMessage,
    OutboxEvent,
    Purpose,
)
from app.modules.messaging.providers import (
    Accepted,
    AmbiguousError,
    PermanentError,
    Providers,
    TemporaryError,
)
from app.modules.messaging.service import Outcome, enqueue, otp_code_key, process
from tests.conftest import Org


class FakeProvider:
    """Counts sends; ``fail_with`` makes every send raise that error."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail_with: Exception | None = None

    def send(self, to: str, *args: str) -> Accepted:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append((to, args[-2]))  # (recipient, text)
        return Accepted(provider_message_id=f"p-{uuid.uuid4().hex}")


Fakes = tuple[FakeProvider, FakeProvider, Providers]


@pytest.fixture
def fakes() -> Fakes:
    sms, email = FakeProvider(), FakeProvider()
    return sms, email, Providers(sms=sms, email=email)


@pytest.fixture
def settings() -> Settings:
    return get_settings()


def queued(
    channel: Channel = Channel.SMS, purpose: Purpose = Purpose.NOTIFICATION, **kw: object
) -> uuid.UUID:
    with SessionLocal() as db:
        message = enqueue(db, channel, purpose, "+989121234567", body="سلام", subject="موضوع", **kw)  # type: ignore[arg-type]
        db.commit()
        return message.id


def run(
    providers: Providers, settings: Settings, message_id: uuid.UUID
) -> tuple[Outcome, int, OutboundMessage]:
    with SessionLocal() as db:
        result = process(db, get_redis(), providers, settings, message_id)
    with SessionLocal() as db:
        message = db.get(OutboundMessage, message_id)
        assert message is not None
        return result.outcome, result.delay, message


@pytest.fixture(autouse=True)
def _clean_messages() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        db.execute(delete(OutboxEvent))
        db.execute(delete(OutboundMessage))
        db.commit()


# -- outbox ------------------------------------------------------------------------


def test_message_and_outbox_row_commit_together() -> None:
    with SessionLocal() as db:
        enqueue(db, Channel.EMAIL, Purpose.NOTIFICATION, "a@example.com", subject="x", body="y")
        db.rollback()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(OutboundMessage)) == 0
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0
    queued()
    with SessionLocal() as db:
        event = db.scalars(select(OutboxEvent)).one()
        assert event.routing_key == "test.messages.send" and event.published_at is None


# -- worker outcomes ----------------------------------------------------------------


def test_success_then_repeated_delivery_does_not_resend(fakes: Fakes, settings: Settings) -> None:
    sms, _, providers = fakes
    message_id = queued()
    outcome, _, message = run(providers, settings, message_id)
    assert outcome is Outcome.DONE and message.status is MessageStatus.ACCEPTED
    assert message.provider_message_id and message.attempts == 1 and message.sent_at
    run(providers, settings, message_id)  # the queue delivered it again
    assert len(sms.sent) == 1


def test_email_goes_to_email_provider(fakes: Fakes, settings: Settings) -> None:
    sms, email, providers = fakes
    run(providers, settings, queued(channel=Channel.EMAIL))
    assert (len(sms.sent), len(email.sent)) == (0, 1)


def test_crash_during_send_becomes_unknown_not_resent(fakes: Fakes, settings: Settings) -> None:
    sms, _, providers = fakes
    message_id = queued()
    with SessionLocal() as db:
        db.get(OutboundMessage, message_id).status = MessageStatus.SENDING  # type: ignore[union-attr]
        db.commit()
    _, _, message = run(providers, settings, message_id)
    assert message.status is MessageStatus.UNKNOWN and sms.sent == []


def test_temporary_errors_retry_with_backoff_then_fail(fakes: Fakes, settings: Settings) -> None:
    sms, _, providers = fakes
    sms.fail_with = TemporaryError("HTTP 503")
    message_id = queued()
    delays = []
    for _ in range(settings.message_max_attempts - 1):
        outcome, delay, message = run(providers, settings, message_id)
        assert outcome is Outcome.RETRY and message.status is MessageStatus.QUEUED
        delays.append(delay)
    assert delays == sorted(delays) and delays[0] > 0
    outcome, _, message = run(providers, settings, message_id)
    assert outcome is Outcome.DEAD and message.status is MessageStatus.FAILED
    assert message.attempts == settings.message_max_attempts and "503" in (message.last_error or "")


def test_permanent_error_fails_without_retry(fakes: Fakes, settings: Settings) -> None:
    sms, _, providers = fakes
    sms.fail_with = PermanentError("HTTP 400: bad number")
    outcome, _, message = run(providers, settings, queued())
    assert (
        outcome is Outcome.DEAD and message.status is MessageStatus.FAILED and message.attempts == 1
    )


def test_lost_response_is_unknown_and_never_resent_blindly(
    fakes: Fakes, settings: Settings
) -> None:
    sms, _, providers = fakes
    sms.fail_with = AmbiguousError("timeout")
    message_id = queued()
    outcome, _, message = run(providers, settings, message_id)
    assert outcome is Outcome.DONE and message.status is MessageStatus.UNKNOWN
    sms.fail_with = None
    run(providers, settings, message_id)
    assert sms.sent == []


# -- OTP through the queue -----------------------------------------------------------


@pytest.fixture
def queue_mode(settings: Settings) -> Iterator[None]:
    previous = settings.messaging_mode
    settings.messaging_mode = "queue"
    yield
    settings.messaging_mode = previous


def test_otp_is_queued_without_storing_the_code(
    org: Org, fakes: Fakes, settings: Settings, queue_mode: None
) -> None:
    sms, _, providers = fakes
    client = TestClient(app)
    r = client.post("/auth/otp/request", json={"channel": "sms", "destination": "09100000003"})
    assert r.status_code == 202
    with SessionLocal() as db:
        message = db.scalars(select(OutboundMessage)).one()
        assert message.purpose is Purpose.OTP and message.body is None
        assert message.recipient == "+989100000003"
        event = db.scalars(select(OutboxEvent)).one()
        assert event.routing_key == "test.messages.otp"
    code = get_redis().get(otp_code_key(message.id))
    assert code and len(str(code)) == 5

    _, _, sent = run(providers, settings, message.id)
    assert sent.status is MessageStatus.ACCEPTED
    assert str(code) in sms.sent[0][1]
    assert get_redis().get(otp_code_key(message.id)) is None  # not kept after sending

    # The delivered code logs the user in.
    verified = client.post(
        "/auth/otp/verify", json={"challenge_id": r.json()["challenge_id"], "code": str(code)}
    )
    assert verified.status_code == 200


def test_superseded_or_expired_otp_is_never_sent(
    org: Org, fakes: Fakes, settings: Settings, queue_mode: None
) -> None:
    sms, _, providers = fakes
    client = TestClient(app)
    client.post("/auth/otp/request", json={"channel": "sms", "destination": "09100000003"})
    get_redis().delete("otp:cooldown:sms:+989100000003")
    client.post("/auth/otp/request", json={"channel": "sms", "destination": "09100000003"})
    with SessionLocal() as db:
        first, second = db.scalars(
            select(OutboundMessage).order_by(OutboundMessage.created_at)
        ).all()
        second.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    _, _, old = run(providers, settings, first.id)
    _, _, late = run(providers, settings, second.id)
    assert (old.status, late.status) == (MessageStatus.EXPIRED, MessageStatus.EXPIRED)
    assert sms.sent == []


# -- delivery reports ----------------------------------------------------------------


def report(client: TestClient, payload: Mapping[str, object], secret: str | None = None) -> int:
    body = json.dumps(payload).encode()
    key = (secret or get_settings().sms_webhook_secret.get_secret_value()).encode()
    signature = hmac.new(key, body, hashlib.sha256).hexdigest()
    response = client.post(
        "/webhooks/sms",
        content=body,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )
    return int(response.status_code)


def test_delivery_reports_are_signed_idempotent_and_never_go_backwards(
    fakes: Fakes, settings: Settings
) -> None:
    _, _, providers = fakes
    _, _, message = run(providers, settings, queued())
    client = TestClient(app)
    payload = {"event_id": "e1", "message_id": message.provider_message_id, "status": "delivered"}

    assert report(client, payload, secret="wrong-secret") == 401  # noqa: S106 - test value
    assert report(client, payload) == 204
    assert report(client, payload) == 204  # same report again
    assert (
        report(client, {**payload, "event_id": "e2", "status": "failed"}) == 204
    )  # late, conflicting
    with SessionLocal() as db:
        current = db.get(OutboundMessage, message.id)
        assert (
            current is not None
            and current.status is MessageStatus.DELIVERED
            and current.delivered_at
        )


def test_admin_message_log(org: Org, fakes: Fakes, settings: Settings) -> None:
    from tests.conftest import login_as

    queued()
    assert login_as(org.admin.id).get("/messages").json()["total"] == 1
    assert login_as(org.manager.id).get("/messages").status_code == 403


# -- RabbitMQ round trip ----------------------------------------------------------------


def test_outbox_to_rabbitmq_to_worker(fakes: Fakes, settings: Settings) -> None:
    """Publisher confirms, a real queue, and the worker step; a retry goes to the retry queue."""
    sms, _, providers = fakes
    connection = broker.connect(settings.rabbitmq_url)
    channel = connection.channel()
    broker.declare(channel)
    for queue in (*broker.work_queues(), "test.messages.send.retry", broker.dead_queue()):
        channel.queue_purge(queue)
    channel.confirm_delivery()
    try:
        ok_id, retry_id = queued(), queued()
        with SessionLocal() as db:
            assert broker.publish_pending(db, channel) == 2
            assert db.scalar(select(func.count()).where(OutboxEvent.published_at.is_(None))) == 0

        delivered = []
        for _ in range(2):
            method, _props, body = channel.basic_get("test.messages.send")
            assert method is not None and body is not None and method.delivery_tag is not None
            message_id = uuid.UUID(json.loads(body)["message_id"])
            sms.fail_with = TemporaryError("HTTP 503") if message_id == retry_id else None
            with SessionLocal() as db:
                result = process(db, get_redis(), providers, settings, message_id)
            broker.route_result(channel, "test.messages.send", body, result)
            channel.basic_ack(method.delivery_tag)
            delivered.append(message_id)
        assert set(delivered) == {ok_id, retry_id}
        retry = channel.queue_declare("test.messages.send.retry", durable=True, passive=True)
        assert retry.method.message_count == 1
    finally:
        for queue in (*broker.work_queues(), "test.messages.send.retry", broker.dead_queue()):
            channel.queue_purge(queue)
        connection.close()


def test_broker_down_keeps_messages_in_outbox() -> None:
    queued()
    with pytest.raises(pika.exceptions.AMQPConnectionError):
        broker.connect("amqp://crm:crm@localhost:1/")
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).where(OutboxEvent.published_at.is_(None))) == 1
