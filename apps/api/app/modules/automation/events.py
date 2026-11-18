"""Recording automation events from domain code (kept tiny to avoid import cycles)."""

import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.automation.models import AutomationEvent


def emit(
    db: Session,
    event_type: str,
    subject_type_: str,
    subject_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
    *,
    depth: int = 0,
    rule_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> None:
    """Records an event in the caller's transaction; it commits with the change."""
    db.execute(
        insert(AutomationEvent)
        .values(
            id=uuid.uuid4(),
            type=event_type,
            subject_type=subject_type_,
            subject_id=subject_id,
            payload=payload or {},
            depth=depth,
            rule_id=rule_id,
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )
