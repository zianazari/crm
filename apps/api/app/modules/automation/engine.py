"""Running automations (spec 4.6; criteria 9, 10, 16, 21).

Guarantees:
* An event runs a rule at most once (unique rule+event), and each action at most once
  per execution (its result is logged before moving on; a repeat run skips it).
* Activation never acts on the past: only events at or after ``active_since`` count,
  and time-based events only for moments after activation.
* A manager's rule only touches records of their own team (the author's scope at run
  time, so a narrowed scope also applies to waiting executions).
* After a delay, the rule's state, the author's scope and every earlier condition are
  checked again before continuing; messages re-check consent when they are sent.
* A failing action stops the run and tells the rule's author.
* Events caused by automations carry a depth; beyond ``MAX_DEPTH`` nothing runs, so
  rules cannot trigger each other in a loop.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.activities.models import OPEN_STATUSES, Activity, ActivityEvent, ActivityType
from app.modules.activities.team_tasks import QueueError, queue_task
from app.modules.automation.events import emit
from app.modules.automation.graph import DELAY_UNITS, subject_type
from app.modules.automation.models import (
    AutomationEvent,
    AutomationExecution,
    AutomationRule,
    ExecutionStatus,
    RepeatPolicy,
    RuleStatus,
)
from app.modules.crm.access import build_scope
from app.modules.crm.models import Customer, Lead
from app.modules.identity.models import Team, User
from app.modules.messaging.models import Channel, Purpose
from app.modules.messaging.service import enqueue
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import notify
from app.modules.sales.models import Deal, DealStatus

logger = logging.getLogger("crm.automation")

MAX_DEPTH = 3
ADVISORY_LOCK = 0x43524D5F41544F  # "CRM_ATO"


# -- events ------------------------------------------------------------------------


# -- the record an execution is about ------------------------------------------------


@dataclass
class Context:
    subject_type: str
    subject: Lead | Customer | Deal | Activity
    owner_id: uuid.UUID
    name: str
    lead: Lead | None = None
    customer: Customer | None = None
    deal: Deal | None = None
    # The stage named by a stage event. The first pass judges the stage that was entered,
    # even if the deal moved on before the worker got to it; re-checks use the live stage.
    entered_stage_id: str | None = None

    @property
    def contact(self) -> Lead | Customer | None:
        return self.customer or self.lead

    @property
    def link(self) -> str:
        if self.deal:
            return f"/deals/{self.deal.id}"
        if self.customer:
            return f"/customers/{self.customer.id}"
        if self.lead:
            return f"/leads/{self.lead.id}"
        return "/activities"


def load_context(db: Session, kind: str, subject_id: uuid.UUID) -> Context | None:
    if kind == "lead":
        lead = db.get(Lead, subject_id)
        return Context(kind, lead, lead.owner_id, lead.full_name, lead=lead) if lead else None
    if kind == "customer":
        customer = db.get(Customer, subject_id)
        if customer is None:
            return None
        return Context(kind, customer, customer.owner_id, customer.full_name, customer=customer)
    if kind == "deal":
        deal = db.get(Deal, subject_id)
        if deal is None:
            return None
        return Context(kind, deal, deal.owner_id, deal.title, customer=deal.customer, deal=deal)
    if kind == "activity":
        activity = db.get(Activity, subject_id)
        if activity is None:
            return None
        return Context(
            kind,
            activity,
            activity.owner_id,
            activity.title,
            lead=activity.lead,
            customer=activity.customer,
            deal=activity.deal,
        )
    return None


def _field_values(ctx: Context, field: str) -> set[str]:
    if field == "owner":
        return {str(ctx.owner_id)}
    if field == "source":
        holder = ctx.customer or ctx.lead
        return {str(holder.source_id)} if holder and holder.source_id else set()
    if field == "tag":
        holder = ctx.customer or ctx.lead
        return {str(t.id) for t in holder.tags} if holder else set()
    if field == "stage":
        if ctx.entered_stage_id:
            return {ctx.entered_stage_id}
        return {str(ctx.deal.stage_id)} if ctx.deal else set()
    if field == "deal_status":
        return {ctx.deal.status.value} if ctx.deal else set()
    if field == "lead_status":
        return {ctx.lead.status.value} if ctx.lead else set()
    return set()


def condition_holds(ctx: Context, config: dict[str, Any]) -> bool:
    actual = _field_values(ctx, str(config.get("field")))
    wanted = {str(v) for v in config.get("values") or []}
    matches = bool(actual & wanted)
    return matches if config.get("operator") == "in" else not matches


# -- actions ----------------------------------------------------------------------------


class ActionError(Exception):
    pass


def render(template: str, ctx: Context) -> str:
    contact = ctx.contact
    values = {
        "name": contact.full_name if contact else ctx.name,
        "deal": ctx.deal.title if ctx.deal else "",
        "owner": ctx.deal.owner.full_name if ctx.deal else "",
    }
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    return result.strip()


def _user_in_scope(db: Session, author: User, user_id: str) -> User:
    user = db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active or not build_scope(db, author).can_assign_to(user):
        raise ActionError("کاربر انتخاب‌شده فعال نیست یا خارج از دامنه سازنده قانون است.")
    return user


def run_action(
    db: Session,
    rule: AutomationRule,
    execution: AutomationExecution,
    ctx: Context,
    step: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    kind, config = step["kind"], step["config"]
    author = rule.created_by
    tz = ZoneInfo(get_settings().timezone)

    if kind == "create_activity" and config.get("assignee") == "team":
        team = db.get(Team, uuid.UUID(str(config["team_id"])))
        if team is None:
            raise ActionError("تیم انتخاب‌شده دیگر وجود ندارد.")
        try:
            task = queue_task(
                db,
                team=team,
                type_=ActivityType(config["activity_type"]),
                title=render(str(config["title"]), ctx),
                description=render(str(config.get("description") or ""), ctx) or None,
                due_date=datetime.now(tz).date()
                + timedelta(days=int(config.get("due_in_days", 0))),
                created_by=author,
                lead=ctx.lead if not ctx.customer else None,
                customer=ctx.customer,
                deal=ctx.deal,
                source={"automation": str(rule.id), "execution": str(execution.id)},
            )
        except QueueError as exc:
            raise ActionError(str(exc)) from exc
        return {"result": "done", "team_task_id": str(task.id), "team": team.name}

    if kind == "create_activity":
        assignee: User | None
        if config.get("assignee") == "user":
            assignee = _user_in_scope(db, author, str(config["user_id"]))
        else:
            assignee = db.get(User, ctx.owner_id)
        if assignee is None or not assignee.is_active:
            raise ActionError("مسئول انجام فعالیت فعال نیست.")
        due = datetime.now(tz).date() + timedelta(days=int(config.get("due_in_days", 0)))
        activity = Activity(
            type=ActivityType(config["activity_type"]),
            title=render(str(config["title"]), ctx)[:200],
            description=(render(str(config.get("description") or ""), ctx) or None),
            owner_id=assignee.id,
            owner=assignee,
            created_by_id=author.id,
            due_date=due,
            lead=ctx.lead if not ctx.customer else None,
            customer=ctx.customer,
            deal=ctx.deal,
        )
        db.add(activity)
        db.flush()
        db.add(
            ActivityEvent(
                activity_id=activity.id,
                kind="created",
                details={"automation": str(rule.id), "execution": str(execution.id)},
                actor_id=author.id,
            )
        )
        notify(
            db,
            assignee.id,
            NotificationKind.ACTIVITY_ASSIGNED,
            f"فعالیت جدید از اتوماسیون «{rule.name}»: {activity.title}",
            f"auto:{execution.id}:{index}:assigned",
            link=ctx.link,
        )
        return {"result": "done", "activity_id": str(activity.id), "assignee": assignee.full_name}

    if kind == "notify":
        recipient: User | None
        if config.get("recipient") == "user":
            recipient = _user_in_scope(db, author, str(config["user_id"]))
        elif config.get("recipient") == "owner_manager":
            owner = db.get(User, ctx.owner_id)
            team = db.get(Team, owner.team_id) if owner and owner.team_id else None
            recipient = db.get(User, team.manager_id) if team and team.manager_id else None
            if recipient is None:
                return {"result": "skipped", "detail": "مسئول پرونده مدیر تیم ندارد."}
        else:
            recipient = db.get(User, ctx.owner_id)
        if recipient is None or not recipient.is_active:
            raise ActionError("گیرنده اعلان فعال نیست.")
        notify(
            db,
            recipient.id,
            NotificationKind.RECORD_ASSIGNED,
            render(str(config["title"]), ctx),
            f"auto:{execution.id}:{index}",
            body=render(str(config.get("body") or ""), ctx)
            or f"اتوماسیون «{rule.name}» — {ctx.name}",
            link=ctx.link,
        )
        return {"result": "done", "recipient": recipient.full_name}

    if kind in {"send_sms", "send_email"}:
        contact = ctx.contact
        channel = Channel.SMS if kind == "send_sms" else Channel.EMAIL
        if contact is None:
            return {"result": "skipped", "detail": "پرونده مخاطبی برای ارسال ندارد."}
        address = contact.mobile if channel is Channel.SMS else contact.email
        # Consent is read now, at sending time, so a withdrawal during a delay counts.
        allowed = contact.sms_consent if channel is Channel.SMS else contact.email_consent
        if not address:
            return {"result": "skipped", "detail": "مخاطب نشانی این کانال را ندارد."}
        if not allowed:
            return {"result": "skipped", "detail": "مخاطب اجازه دریافت این پیام را نداده است."}
        message = enqueue(
            db,
            channel,
            Purpose.NOTIFICATION,
            address,
            subject=render(str(config.get("subject") or ""), ctx) or None,
            body=render(str(config["text"]), ctx),
        )
        return {"result": "done", "message_id": str(message.id), "to": address}

    raise ActionError(f"unknown action {kind}")


# -- execution ---------------------------------------------------------------------------


def _finish(
    execution: AutomationExecution, status: ExecutionStatus, error: str | None = None
) -> None:
    execution.status = status
    execution.error = error[:500] if error else None
    execution.finished_at = datetime.now(UTC)
    execution.resume_at = None


def _log(execution: AutomationExecution, entry: dict[str, Any]) -> None:
    execution.log = [*execution.log, {**entry, "at": datetime.now(UTC).isoformat()}]


def _done_steps(execution: AutomationExecution) -> set[int]:
    return {
        int(e["step"]) for e in execution.log if e.get("result") in {"done", "skipped", "passed"}
    }


def run_execution(db: Session, execution: AutomationExecution, now: datetime) -> None:
    rule = db.get(AutomationRule, execution.rule_id)
    if rule is None or rule.status is not RuleStatus.ACTIVE:
        _finish(execution, ExecutionStatus.CANCELED, "قانون متوقف شده است.")
        db.commit()
        return
    ctx = load_context(db, execution.subject_type, execution.subject_id)
    if ctx is None:
        _finish(execution, ExecutionStatus.SKIPPED, "پرونده پیدا نشد.")
        db.commit()
        return
    if (
        not build_scope(db, rule.created_by).has_full_access(ctx.owner_id)
        or not rule.created_by.is_active
    ):
        _finish(execution, ExecutionStatus.SKIPPED, "پرونده خارج از دامنه سازنده قانون است.")
        db.commit()
        return

    steps = execution.version.definition["steps"]
    resuming = execution.status is ExecutionStatus.WAITING
    if resuming:
        # Things may have changed during the delay: every earlier condition must still hold.
        for step in steps[: execution.step]:
            if step["kind"] == "condition" and not condition_holds(ctx, step["config"]):
                _log(execution, {"step": execution.step, "type": "recheck", "result": "failed"})
                _finish(execution, ExecutionStatus.SKIPPED, "شرایط پس از تأخیر دیگر برقرار نیست.")
                db.commit()
                return
        execution.status = ExecutionStatus.RUNNING
    else:
        event = db.get(AutomationEvent, execution.event_id)
        if event is not None and event.type == "deal.stage_entered":
            ctx.entered_stage_id = event.payload.get("stage_id")

    done = _done_steps(execution)
    while execution.step < len(steps):
        index, step = execution.step, steps[execution.step]
        if index in done:
            execution.step += 1
            continue
        kind = step["kind"]
        if kind == "condition":
            if not condition_holds(ctx, step["config"]):
                _log(execution, {"step": index, "type": kind, "result": "not_met"})
                _finish(execution, ExecutionStatus.SKIPPED, None)
                db.commit()
                return
            _log(execution, {"step": index, "type": kind, "result": "passed"})
        elif kind == "delay":
            seconds = int(step["config"]["amount"]) * DELAY_UNITS[str(step["config"]["unit"])]
            _log(execution, {"step": index, "type": kind, "result": "done", "seconds": seconds})
            execution.step += 1
            execution.status = ExecutionStatus.WAITING
            execution.resume_at = now + timedelta(seconds=seconds)
            db.commit()
            return
        else:
            try:
                outcome = run_action(db, rule, execution, ctx, step, index)
            except ActionError as exc:
                db.rollback()
                execution = db.get(AutomationExecution, execution.id)  # type: ignore[assignment]
                assert execution is not None  # noqa: S101
                _log(
                    execution, {"step": index, "type": kind, "result": "failed", "detail": str(exc)}
                )
                _finish(execution, ExecutionStatus.FAILED, str(exc))
                notify(
                    db,
                    rule.created_by_id,
                    NotificationKind.RECORD_ASSIGNED,
                    f"اجرای اتوماسیون «{rule.name}» متوقف شد",
                    f"auto-failed:{execution.id}",
                    body=str(exc),
                    link=f"/automations/{rule.id}",
                )
                db.commit()
                return
            _log(execution, {"step": index, "type": kind, **outcome})
        execution.step += 1
        db.commit()
    _finish(execution, ExecutionStatus.COMPLETED)
    db.commit()


def start_execution(
    db: Session, rule: AutomationRule, event: AutomationEvent, now: datetime
) -> None:
    version = rule.active_version
    if version is None:
        return
    execution_id = uuid.uuid4()
    inserted = db.execute(
        insert(AutomationExecution)
        .values(
            id=execution_id,
            rule_id=rule.id,
            version_id=version.id,
            event_id=event.id,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            depth=event.depth,
            log=[],
        )
        .on_conflict_do_nothing(index_elements=["rule_id", "event_id"])
        .returning(AutomationExecution.id)
    ).scalar()
    if inserted is None:
        return  # this event already ran this rule
    execution = db.get(AutomationExecution, execution_id)
    assert execution is not None  # noqa: S101

    reason = None
    if event.depth > MAX_DEPTH:
        reason = "زنجیره اتوماسیون‌ها از حد مجاز عمیق‌تر شد (جلوگیری از حلقه)."
    elif rule.repeat_policy is RepeatPolicy.ONCE_PER_RECORD and db.scalar(
        select(func.count()).where(
            AutomationExecution.rule_id == rule.id,
            AutomationExecution.subject_id == event.subject_id,
            AutomationExecution.id != execution.id,
            AutomationExecution.status != ExecutionStatus.SKIPPED,
        )
    ):
        reason = "این قانون قبلاً برای این پرونده اجرا شده است."
    elif (
        db.scalar(
            select(func.count()).where(
                AutomationExecution.rule_id == rule.id,
                AutomationExecution.created_at >= now - timedelta(hours=1),
            )
        )
        or 0
    ) > rule.max_runs_per_hour:
        reason = "سقف اجرای ساعتی قانون پر شده است."
    if reason:
        _finish(execution, ExecutionStatus.SKIPPED, reason)
        db.commit()
        return
    db.commit()
    run_execution(db, execution, now)


def _matches(rule: AutomationRule, event: AutomationEvent) -> bool:
    if rule.active_version is None or rule.active_since is None:
        return False
    if event.rule_id is not None and event.rule_id != rule.id:
        return False
    if event.created_at < rule.active_since:
        return False
    trigger = rule.active_version.definition["trigger"]
    if trigger.get("event") != event.type:
        return False
    if subject_type(trigger) != event.subject_type:
        return False
    # Time-based moments must fall after activation (never retroactive).
    moment = event.payload.get("moment")
    return not (moment and datetime.fromisoformat(moment) < rule.active_since)


def process_events(db: Session, now: datetime, limit: int = 200) -> int:
    events = list(
        db.scalars(
            select(AutomationEvent)
            .where(AutomationEvent.processed_at.is_(None))
            .order_by(AutomationEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    if not events:
        return 0
    rules = list(
        db.scalars(
            select(AutomationRule).where(AutomationRule.status == RuleStatus.ACTIVE)
        ).unique()
    )
    for event in events:
        event.processed_at = now
    db.commit()
    for event in events:
        for rule in rules:
            if _matches(rule, event):
                try:
                    start_execution(db, rule, event, now)
                except Exception:
                    db.rollback()
                    logger.exception("Automation %s failed on event %s", rule.id, event.id)
    return len(events)


def resume_waiting(db: Session, now: datetime, limit: int = 200) -> int:
    waiting = list(
        db.scalars(
            select(AutomationExecution)
            .where(
                AutomationExecution.status == ExecutionStatus.WAITING,
                AutomationExecution.resume_at <= now,
            )
            .limit(limit)
            .with_for_update(skip_locked=True, of=AutomationExecution)
        ).unique()
    )
    for execution in waiting:
        run_execution(db, execution, now)
    return len(waiting)


def scan_time_events(db: Session, now: datetime) -> None:
    """Emits activity-due and deal-inactivity events for active rules (spec 4.6)."""
    rules = [
        r
        for r in db.scalars(
            select(AutomationRule).where(AutomationRule.status == RuleStatus.ACTIVE)
        ).unique()
        if r.active_version and r.active_since
    ]
    events = {
        r.active_version.definition["trigger"].get("event") for r in rules if r.active_version
    }
    if "activity.due" in events:
        since = min(r.active_since for r in rules if r.active_since) or now
        window = max(since, now - timedelta(days=1))
        # Date-only activities fall due at 09:00 local, like their reminders.
        anchor_untimed = func.timezone(
            get_settings().timezone, Activity.due_date + literal_column("time '09:00'")
        )
        due_moment = func.coalesce(Activity.start_at, anchor_untimed)
        for activity_id, moment in db.execute(
            select(Activity.id, due_moment).where(
                Activity.status.in_(OPEN_STATUSES), due_moment <= now, due_moment >= window
            )
        ):
            emit(
                db,
                "activity.due",
                "activity",
                activity_id,
                {"moment": moment.isoformat()},
                dedupe_key=f"activity.due:{activity_id}:{moment.isoformat()}",
            )
    for rule in rules:
        trigger = rule.active_version.definition["trigger"] if rule.active_version else {}
        if trigger.get("event") != "deal.inactive" or rule.active_since is None:
            continue
        days = int(trigger.get("days", 3))
        last = func.coalesce(Deal.last_activity_at, Deal.created_at)
        threshold = last + timedelta(days=days)
        for deal_id, moment in db.execute(
            select(Deal.id, threshold).where(
                Deal.status == DealStatus.OPEN,
                Deal.archived_at.is_(None),
                threshold <= now,
                threshold >= rule.active_since,
            )
        ):
            emit(
                db,
                "deal.inactive",
                "deal",
                deal_id,
                {"moment": moment.isoformat(), "days": days},
                rule_id=rule.id,
                dedupe_key=f"deal.inactive:{rule.id}:{deal_id}:{moment.isoformat()}",
            )
    db.commit()


def tick(db: Session, now: datetime | None = None) -> bool:
    """One pass of the engine; only one worker runs it at a time.

    The engine commits many times, and every commit hands the session's connection back
    to the pool, so the lock lives on its own connection held for the whole pass (it is
    released with that connection if the process dies).
    """
    now = now or datetime.now(UTC)
    bind = db.get_bind()
    with (bind.engine if isinstance(bind, Connection) else bind).connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK}):
            return False
        try:
            scan_time_events(db, now)
            process_events(db, now)
            resume_waiting(db, now)
        finally:
            db.rollback()
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK})
            lock.commit()
    return True
