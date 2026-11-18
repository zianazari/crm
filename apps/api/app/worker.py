"""Background worker: publishes the outbox to RabbitMQ and sends queued messages.

    uv run python -m app.worker

Run as many as needed; each delivery is processed safely more than once.
"""

import logging
import signal
import threading
import time
import uuid

import pika.exceptions
from sqlalchemy.exc import SQLAlchemyError

import app.db.models  # noqa: F401 - registers every table so foreign keys resolve
from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.modules.messaging import broker
from app.modules.messaging.providers import build_providers
from app.modules.messaging.service import Result, process

logger = logging.getLogger("crm.worker")
stopping = threading.Event()


def publisher_loop(url: str) -> None:
    while not stopping.is_set():
        try:
            connection = broker.connect(url)
            channel = connection.channel()
            broker.declare(channel)
            channel.confirm_delivery()
            while not stopping.is_set():
                with SessionLocal() as db:
                    sent = broker.publish_pending(db, channel)
                connection.process_data_events(time_limit=0 if sent else 0.5)
            connection.close()
        except (pika.exceptions.AMQPError, SQLAlchemyError, OSError):
            logger.exception("Outbox publisher error; retrying in 2s")
            stopping.wait(2)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    redis = get_redis()
    providers = build_providers(settings)
    url = settings.rabbitmq_url

    def handle(message_id: uuid.UUID) -> Result:
        with SessionLocal() as db:
            return process(db, redis, providers, settings, message_id)

    threading.Thread(target=publisher_loop, args=(url,), daemon=True, name="outbox").start()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())

    while not stopping.is_set():
        try:
            connection = broker.connect(url)
            channel = connection.channel()
            broker.declare(channel)
            logger.info("Worker consuming %s", ", ".join(broker.work_queues()))
            consumer = threading.Thread(target=broker.consume, args=(channel, handle), daemon=True)
            consumer.start()
            while consumer.is_alive() and not stopping.is_set():
                time.sleep(0.5)
            if stopping.is_set():
                connection.add_callback_threadsafe(channel.stop_consuming)
                consumer.join(timeout=5)
                connection.close()
        except pika.exceptions.AMQPError:
            logger.exception("Broker connection lost; reconnecting in 2s")
            stopping.wait(2)
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
