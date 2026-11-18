"""Automation rules, published versions, domain events and executions (spec 4.6, 9).

* A rule has an editable draft (the builder graph, positions included). Publishing
  compiles the graph into an immutable ``RuleVersion``; the active version only changes
  on the next publish.
* Domain code records ``AutomationEvent`` rows in the same transaction as the change.
  The worker matches them to active rules and runs one ``AutomationExecution`` per
  (rule, event) — the unique key makes repeated processing harmless.
* Executions are linear: conditions and actions run in order; a delay parks the
  execution until ``resume_at``.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.identity.models import User


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class RuleStatus(enum.StrEnum):
    DRAFT = "draft"  # never published
    ACTIVE = "active"
    PAUSED = "paused"


class RepeatPolicy(enum.StrEnum):
    EVERY_TIME = "every_time"  # each qualifying event runs the rule
    ONCE_PER_RECORD = "once_per_record"  # at most one run per record, ever


class ExecutionStatus(enum.StrEnum):
    RUNNING = "running"
    WAITING = "waiting"  # parked by a delay
    COMPLETED = "completed"
    SKIPPED = "skipped"  # a condition did not hold, or a limit applied
    FAILED = "failed"
    CANCELED = "canceled"  # the rule was paused during a delay


class AutomationRule(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "automation_rules"

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RuleStatus] = mapped_column(
        _enum(RuleStatus, "automation_status"), default=RuleStatus.DRAFT
    )
    repeat_policy: Mapped[RepeatPolicy] = mapped_column(
        _enum(RepeatPolicy, "automation_repeat"), default=RepeatPolicy.EVERY_TIME
    )
    max_runs_per_hour: Mapped[int] = mapped_column(default=500)
    # Builder graph being edited: {"nodes": [...], "edges": [...]}
    draft: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    draft_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_rule_versions.id", use_alter=True, ondelete="SET NULL")
    )
    # Only events after this moment are handled: activation never acts retroactively.
    active_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    created_by: Mapped[User] = relationship(lazy="joined")
    active_version: Mapped["RuleVersion | None"] = relationship(
        foreign_keys=[active_version_id], lazy="joined", post_update=True
    )


class RuleVersion(UUIDPrimaryKey, Base):
    """Immutable: the compiled definition that runs, and the layout it came from."""

    __tablename__ = "automation_rule_versions"
    __table_args__ = (UniqueConstraint("rule_id", "number"),)

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int]
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    layout: Mapped[dict[str, Any]] = mapped_column(JSONB)
    published_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    published_by: Mapped[User] = relationship(lazy="joined")


class AutomationEvent(UUIDPrimaryKey, Base):
    __tablename__ = "automation_events"

    type: Mapped[str] = mapped_column(String(40), index=True)
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Events produced by an automation's own actions carry depth + 1 (loop guard).
    depth: Mapped[int] = mapped_column(default=0)
    # Time-based events target one rule and use a key so a scan never repeats them.
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AutomationExecution(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "automation_executions"
    __table_args__ = (UniqueConstraint("rule_id", "event_id"),)

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_rule_versions.id"))
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_events.id"))
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[ExecutionStatus] = mapped_column(
        _enum(ExecutionStatus, "automation_execution_status"),
        default=ExecutionStatus.RUNNING,
        index=True,
    )
    step: Mapped[int] = mapped_column(default=0)  # next step to run
    resume_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    depth: Mapped[int] = mapped_column(default=0)
    # One entry per step: {"step", "type", "result", "detail", "at", ...ids created}
    log: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(String(500))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    version: Mapped[RuleVersion] = relationship(lazy="joined")
