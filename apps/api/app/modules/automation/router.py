"""Automation rules API (spec 4.6). Managers and admins only; a manager sees and edits
the rules they created, an admin all rules."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.audit.service import audit
from app.modules.auth.deps import DbDep, client_ip, require_csrf
from app.modules.automation.engine import condition_holds, load_context, render
from app.modules.automation.graph import DELAY_UNITS, compile_graph, subject_type
from app.modules.automation.models import (
    AutomationExecution,
    AutomationRule,
    ExecutionStatus,
    RepeatPolicy,
    RuleStatus,
    RuleVersion,
)
from app.modules.automation.templates import TEMPLATES, build_template
from app.modules.crm.access import AccessScope
from app.modules.crm.common import ScopeDep, paginate
from app.modules.crm.schemas import Page, UserRef
from app.modules.identity.models import User

router = APIRouter(prefix="/automations", tags=["automation"], dependencies=[Depends(require_csrf)])


class ProblemOut(BaseModel):
    node_id: str | None
    message: str


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    published_by: UserRef
    published_at: datetime


class RuleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    status: RuleStatus
    trigger_event: str | None = None
    active_version: VersionOut | None
    created_by: UserRef
    updated_at: datetime
    runs_last_30_days: int = 0
    failures_last_30_days: int = 0


class RuleDetail(RuleSummary):
    repeat_policy: RepeatPolicy
    max_runs_per_hour: int
    draft: dict[str, Any]
    draft_updated_at: datetime | None
    active_since: datetime | None
    unpublished_changes: bool = False
    problems: list[ProblemOut] = []


class RuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    template: str | None = None


class DraftIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    repeat_policy: RepeatPolicy = RepeatPolicy.EVERY_TIME
    max_runs_per_hour: int = Field(default=500, ge=1, le=10000)
    graph: dict[str, Any]


class TestIn(BaseModel):
    subject_id: uuid.UUID


class TestStep(BaseModel):
    node_id: str
    kind: str
    outcome: Literal["passed", "not_met", "would_run", "would_skip", "wait", "stopped"]
    detail: str


class TestResult(BaseModel):
    problems: list[ProblemOut]
    subject: str | None = None
    steps: list[TestStep] = []


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ExecutionStatus
    subject_type: str
    subject_id: uuid.UUID
    subject_name: str | None = None
    version_number: int = 0
    log: list[dict[str, Any]]
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    resume_at: datetime | None


# -- helpers ------------------------------------------------------------------------


def _require_manager(scope: AccessScope) -> None:
    if not (scope.is_admin or scope.is_manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="اتوماسیون با مدیر فروش و ادمین است.")


def _load(
    db: Session, scope: AccessScope, rule_id: uuid.UUID, *, lock: bool = False
) -> AutomationRule:
    _require_manager(scope)
    query = select(AutomationRule).where(AutomationRule.id == rule_id)
    if lock:
        query = query.with_for_update(of=AutomationRule)
    rule = db.scalar(query)
    if rule is None or (not scope.is_admin and rule.created_by_id != scope.user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="اتوماسیون پیدا نشد.")
    return rule


def _counts(db: Session, rule_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    if not rule_ids:
        return {}
    since = datetime.now(UTC) - timedelta(days=30)
    rows = db.execute(
        select(
            AutomationExecution.rule_id,
            func.count(),
            func.count().filter(AutomationExecution.status == ExecutionStatus.FAILED),
        )
        .where(
            AutomationExecution.rule_id.in_(rule_ids),
            AutomationExecution.created_at >= since,
        )
        .group_by(AutomationExecution.rule_id)
    )
    return {rid: (int(total), int(failed)) for rid, total, failed in rows}


def _summary(rule: AutomationRule, counts: dict[uuid.UUID, tuple[int, int]]) -> dict[str, Any]:
    trigger = (rule.active_version.definition["trigger"] if rule.active_version else None) or next(
        (n.get("config") for n in rule.draft.get("nodes", []) if n.get("kind") == "trigger"), None
    )
    total, failed = counts.get(rule.id, (0, 0))
    return {
        "trigger_event": (trigger or {}).get("event"),
        "runs_last_30_days": total,
        "failures_last_30_days": failed,
    }


def _detail(db: Session, rule: AutomationRule) -> RuleDetail:
    compiled = compile_graph(rule.draft)
    base = RuleDetail.model_validate(rule)
    for key, value in _summary(rule, _counts(db, [rule.id])).items():
        setattr(base, key, value)
    base.problems = [ProblemOut(node_id=p.node_id, message=p.message) for p in compiled.problems]
    base.unpublished_changes = (
        rule.active_version is None or rule.active_version.layout != rule.draft
    )
    return base


def _check_action_users(
    db: Session, scope: AccessScope, definition: dict[str, Any]
) -> list[ProblemOut]:
    """The server re-checks what each action may do, independently of the builder."""
    problems = []
    for step in definition["steps"]:
        user_id = step["config"].get("user_id")
        if step["kind"] in {"create_activity", "notify"} and user_id:
            user = db.get(User, uuid.UUID(str(user_id)))
            if user is None or not scope.can_assign_to(user):
                problems.append(
                    ProblemOut(node_id=step["node_id"], message="این کاربر خارج از دامنه شما است.")
                )
    return problems


# -- endpoints ---------------------------------------------------------------------------


@router.get("/templates")
def list_templates(scope: ScopeDep) -> list[dict[str, str]]:
    _require_manager(scope)
    return [
        {"key": key, "name": t["name"], "description": t["description"]}
        for key, t in TEMPLATES.items()
    ]


@router.get("")
def list_rules(db: DbDep, scope: ScopeDep) -> list[RuleSummary]:
    _require_manager(scope)
    query = select(AutomationRule).order_by(AutomationRule.updated_at.desc())
    if not scope.is_admin:
        query = query.where(AutomationRule.created_by_id == scope.user.id)
    rules = list(db.scalars(query).unique())
    counts = _counts(db, [r.id for r in rules])
    result = []
    for rule in rules:
        item = RuleSummary.model_validate(rule)
        for key, value in _summary(rule, counts).items():
            setattr(item, key, value)
        result.append(item)
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleCreate, request: Request, db: DbDep, scope: ScopeDep) -> RuleDetail:
    _require_manager(scope)
    if body.template and body.template not in TEMPLATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="قالب نامعتبر است.")
    graph = build_template(db, body.template) if body.template else {"nodes": [], "edges": []}
    rule = AutomationRule(
        name=body.name.strip(),
        description=body.description
        or (TEMPLATES[body.template]["description"] if body.template else None),
        draft=graph,
        draft_updated_at=datetime.now(UTC),
        created_by_id=scope.user.id,
        created_by=scope.user,
    )
    db.add(rule)
    db.flush()
    audit(
        db,
        "automation.created",
        scope.user.id,
        "automation",
        rule.id,
        {"template": body.template},
        client_ip(request),
    )
    db.commit()
    return _detail(db, rule)


@router.get("/{rule_id}")
def get_rule(rule_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> RuleDetail:
    return _detail(db, _load(db, scope, rule_id))


@router.put("/{rule_id}/draft")
def save_draft(rule_id: uuid.UUID, body: DraftIn, db: DbDep, scope: ScopeDep) -> RuleDetail:
    """Saves the builder graph as it is (positions included); the active version is untouched."""
    rule = _load(db, scope, rule_id, lock=True)
    if len(body.graph.get("nodes") or []) > 50:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="حداکثر ۵۰ بلوک مجاز است."
        )
    rule.name = body.name.strip()
    rule.description = body.description
    rule.repeat_policy = body.repeat_policy
    rule.max_runs_per_hour = body.max_runs_per_hour
    rule.draft = {"nodes": body.graph.get("nodes") or [], "edges": body.graph.get("edges") or []}
    rule.draft_updated_at = datetime.now(UTC)
    db.commit()
    return _detail(db, rule)


@router.post("/{rule_id}/publish", responses={422: {"description": "Problems in the graph"}})
def publish(rule_id: uuid.UUID, request: Request, db: DbDep, scope: ScopeDep) -> RuleDetail:
    """Compiles the draft into a new version and activates it. Activation only affects
    events from now on (criterion 21)."""
    rule = _load(db, scope, rule_id, lock=True)
    compiled = compile_graph(rule.draft)
    problems = [ProblemOut(node_id=p.node_id, message=p.message) for p in compiled.problems]
    if compiled.definition is not None:
        problems += _check_action_users(db, scope, compiled.definition)
    if problems or compiled.definition is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "اتوماسیون ایراد دارد.",
                "problems": [p.model_dump() for p in problems],
            },
        )
    number = (
        db.scalar(select(func.max(RuleVersion.number)).where(RuleVersion.rule_id == rule.id)) or 0
    ) + 1
    version = RuleVersion(
        rule_id=rule.id,
        number=number,
        definition=compiled.definition,
        layout=rule.draft,
        published_by_id=scope.user.id,
        published_by=scope.user,
    )
    db.add(version)
    db.flush()
    was_active = rule.status is RuleStatus.ACTIVE
    rule.active_version_id, rule.active_version = version.id, version
    rule.status = RuleStatus.ACTIVE
    if not was_active:
        rule.active_since = datetime.now(UTC)
    audit(
        db,
        "automation.published",
        scope.user.id,
        "automation",
        rule.id,
        {"version": number},
        client_ip(request),
    )
    db.commit()
    return _detail(db, rule)


@router.post("/{rule_id}/pause")
def pause(rule_id: uuid.UUID, request: Request, db: DbDep, scope: ScopeDep) -> RuleDetail:
    """Stops new runs and cancels runs waiting on a delay; history is kept (criterion 21)."""
    rule = _load(db, scope, rule_id, lock=True)
    if rule.status is RuleStatus.ACTIVE:
        rule.status = RuleStatus.PAUSED
        canceled = db.scalars(
            update(AutomationExecution)
            .where(
                AutomationExecution.rule_id == rule.id,
                AutomationExecution.status == ExecutionStatus.WAITING,
            )
            .values(
                status=ExecutionStatus.CANCELED,
                error="قانون متوقف شد.",
                finished_at=datetime.now(UTC),
            )
            .returning(AutomationExecution.id)
        ).all()
        audit(
            db,
            "automation.paused",
            scope.user.id,
            "automation",
            rule.id,
            {"canceled_waiting": len(canceled)},
            client_ip(request),
        )
        db.commit()
    return _detail(db, rule)


@router.post("/{rule_id}/resume")
def resume(rule_id: uuid.UUID, request: Request, db: DbDep, scope: ScopeDep) -> RuleDetail:
    """Re-activates the last published version for events from now on."""
    rule = _load(db, scope, rule_id, lock=True)
    if rule.active_version is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="ابتدا اتوماسیون را منتشر کنید.")
    if rule.status is not RuleStatus.ACTIVE:
        rule.status = RuleStatus.ACTIVE
        rule.active_since = datetime.now(UTC)
        audit(
            db, "automation.resumed", scope.user.id, "automation", rule.id, None, client_ip(request)
        )
        db.commit()
    return _detail(db, rule)


@router.post("/{rule_id}/test")
def dry_run(rule_id: uuid.UUID, body: TestIn, db: DbDep, scope: ScopeDep) -> TestResult:
    """Walks the draft against a real record without creating or sending anything."""
    rule = _load(db, scope, rule_id)
    compiled = compile_graph(rule.draft)
    if compiled.definition is None:
        return TestResult(
            problems=[ProblemOut(node_id=p.node_id, message=p.message) for p in compiled.problems]
        )
    kind = subject_type(compiled.definition["trigger"])
    ctx = load_context(db, kind, body.subject_id)
    if ctx is None or not scope.has_full_access(ctx.owner_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="پرونده پیدا نشد یا خارج از دامنه شما است."
        )
    steps: list[TestStep] = []
    for step in compiled.definition["steps"]:
        node, config, k = step["node_id"], step["config"], step["kind"]
        if k == "condition":
            ok = condition_holds(ctx, config)
            steps.append(
                TestStep(
                    node_id=node,
                    kind=k,
                    outcome="passed" if ok else "not_met",
                    detail="شرط برقرار است." if ok else "شرط برقرار نیست؛ اجرا همین‌جا متوقف می‌شود.",
                )
            )
            if not ok:
                break
        elif k == "delay":
            seconds = int(config["amount"]) * DELAY_UNITS[str(config["unit"])]
            steps.append(
                TestStep(node_id=node, kind=k, outcome="wait", detail=f"{seconds // 60} دقیقه صبر")
            )
        elif k == "create_activity":
            steps.append(
                TestStep(
                    node_id=node,
                    kind=k,
                    outcome="would_run",
                    detail=f"فعالیت «{render(str(config['title']), ctx)}» ساخته می‌شود.",
                )
            )
        elif k == "notify":
            steps.append(
                TestStep(
                    node_id=node,
                    kind=k,
                    outcome="would_run",
                    detail=f"اعلان «{render(str(config['title']), ctx)}» ارسال می‌شود.",
                )
            )
        else:
            contact = ctx.contact
            sms = k == "send_sms"
            address = (contact.mobile if sms else contact.email) if contact else None
            consent = bool(contact) and (contact.sms_consent if sms else contact.email_consent)  # type: ignore[union-attr]
            if not address or not consent:
                steps.append(
                    TestStep(
                        node_id=node,
                        kind=k,
                        outcome="would_skip",
                        detail="نشانی یا اجازه دریافت ثبت نشده؛ پیام ارسال نمی‌شود.",
                    )
                )
            else:
                steps.append(
                    TestStep(
                        node_id=node,
                        kind=k,
                        outcome="would_run",
                        detail=f"به {address}: {render(str(config['text']), ctx)}",
                    )
                )
    return TestResult(problems=[], subject=ctx.name, steps=steps)


@router.get("/{rule_id}/executions")
def executions(
    rule_id: uuid.UUID,
    db: DbDep,
    scope: ScopeDep,
    status_: Annotated[ExecutionStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[ExecutionOut]:
    rule = _load(db, scope, rule_id)
    query = (
        select(AutomationExecution)
        .where(AutomationExecution.rule_id == rule.id)
        .order_by(AutomationExecution.created_at.desc(), AutomationExecution.id)
    )
    if status_:
        query = query.where(AutomationExecution.status == status_)
    rows, total = paginate(db, query, page, page_size)
    items = []
    for row in rows:
        out = ExecutionOut.model_validate(row)
        ctx = load_context(db, row.subject_type, row.subject_id)
        out.subject_name = ctx.name if ctx and scope.has_full_access(ctx.owner_id) else None
        out.version_number = row.version.number
        items.append(out)
    return Page[ExecutionOut](items=items, total=total, page=page, page_size=page_size)


@router.get("/{rule_id}/versions")
def versions(rule_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> list[VersionOut]:
    rule = _load(db, scope, rule_id)
    rows = db.scalars(
        select(RuleVersion)
        .where(RuleVersion.rule_id == rule.id)
        .order_by(RuleVersion.number.desc())
    )
    return [VersionOut.model_validate(v) for v in rows]
