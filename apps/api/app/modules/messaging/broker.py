"""RabbitMQ topology, outbox publisher and consumer (spec 7).

Topology (all durable, messages persistent):
  exchange "crm" (direct)
  messages.otp / messages.send            work queues
  messages.otp.retry / messages.send.retry  hold a message for its backoff (per-message
                                          TTL) and dead-letter it back to the work queue
  messages.dead                           final failures, kept for inspection
"""

import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pika
from pika.adapters.blocking_connection import BlockingChannel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.messaging.models import OutboxEvent
from app.modules.messaging.service import OTP_QUEUE, SEND_QUEUE, Outcome, Result, namespaced

logger = logging.getLogger("crm.messaging.broker")


def exchange() -> str:
    return namespaced("crm")


def dead_queue() -> str:
    return namespaced("messages.dead")


def work_queues() -> tuple[str, str]:
    return namespaced(OTP_QUEUE), namespaced(SEND_QUEUE)


def connect(url: str) -> pika.BlockingConnection:
    params = pika.URLParameters(url)
    params.heartbeat = 30
    params.blocked_connection_timeout = 30
    return pika.BlockingConnection(params)


def declare(channel: BlockingChannel) -> None:
    channel.exchange_declare(exchange(), exchange_type="direct", durable=True)
    for queue in work_queues():
        channel.queue_declare(queue, durable=True)
        channel.queue_bind(queue, exchange(), routing_key=queue)
        channel.queue_declare(
            f"{queue}.retry",
            durable=True,
            arguments={"x-dead-letter-exchange": exchange(), "x-dead-letter-routing-key": queue},
        )
    channel.queue_declare(dead_queue(), durable=True)


def _properties(**extra: Any) -> pika.BasicProperties:
    return pika.BasicProperties(content_type="application/json", delivery_mode=2, **extra)


def publish_pending(db: Session, channel: BlockingChannel, limit: int = 100) -> int:
    """Moves committed outbox rows to RabbitMQ with publisher confirms. A row is marked
    published only after the broker confirmed it, so nothing is lost if the broker is
    down; a crash between confirm and commit only causes a repeat, which the worker
    tolerates."""
    rows = db.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        row.publish_attempts += 1
        channel.basic_publish(
            exchange(),
            row.routing_key,
            json.dumps(row.payload).encode(),
            properties=_properties(message_id=str(row.id)),
            mandatory=True,
        )
        row.published_at = datetime.now(UTC)
        db.commit()
    db.commit()
    return len(rows)


def route_result(channel: BlockingChannel, queue: str, body: bytes, result: Result) -> None:
    if result.outcome is Outcome.RETRY:
        channel.basic_publish(
            "", f"{queue}.retry", body, properties=_properties(expiration=str(result.delay * 1000))
        )
    elif result.outcome is Outcome.DEAD:
        channel.basic_publish("", dead_queue(), body, properties=_properties())


def consume(
    channel: BlockingChannel, handler: Callable[[uuid.UUID], Result], prefetch: int = 10
) -> None:
    channel.basic_qos(prefetch_count=prefetch)

    def on_message(ch: BlockingChannel, method: Any, _props: Any, body: bytes) -> None:
        queue = method.routing_key
        try:
            message_id = uuid.UUID(json.loads(body)["message_id"])
        except (ValueError, KeyError, TypeError):
            logger.error("Malformed queue message on %s; parked in %s", queue, dead_queue())
            ch.basic_publish("", dead_queue(), body, properties=_properties())
            ch.basic_ack(method.delivery_tag)
            return
        try:
            result = handler(message_id)
        except Exception:
            # Database or Redis trouble: hand the delivery back and slow down.
            logger.exception("Processing %s failed; returning it to the queue", message_id)
            time.sleep(1)
            ch.basic_nack(method.delivery_tag, requeue=True)
            return
        route_result(ch, queue, body, result)
        ch.basic_ack(method.delivery_tag)

    for queue in work_queues():
        channel.basic_consume(queue, on_message)
    channel.start_consuming()
