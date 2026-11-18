"""The default rule templates from spec 4.6, as builder graphs (laid out top to bottom)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.models import Team, TeamKind
from app.modules.sales.models import Stage

TEMPLATES: dict[str, dict[str, Any]] = {
    "first_call": {
        "name": "تماس اول با مشتری احتمالی جدید",
        "description": "با ثبت مشتری احتمالی، وظیفه اولین تماس برای مسئول او ساخته می‌شود.",
        "steps": [
            ("trigger", {"event": "lead.created"}),
            (
                "create_activity",
                {
                    "activity_type": "call",
                    "title": "اولین تماس با {name}",
                    "due_in_days": 0,
                    "assignee": "record_owner",
                },
            ),
        ],
    },
    "due_reminder": {
        "name": "اعلان رسیدن موعد پیگیری",
        "description": "وقتی موعد یک فعالیت می‌رسد، به کارشناس اعلان داده می‌شود.",
        "steps": [
            ("trigger", {"event": "activity.due"}),
            ("notify", {"recipient": "record_owner", "title": "موعد «{name}» رسیده است"}),
        ],
    },
    "proposal_follow_up": {
        "name": "پیگیری دو روز پس از پیشنهاد قیمت",
        "description": "با ورود فروش به «پیشنهاد قیمت»، پیگیری دو روز بعد ساخته می‌شود.",
        "steps": [
            ("trigger", {"event": "deal.stage_entered"}),
            ("condition", {"field": "stage", "operator": "in", "values": ["stage:پیشنهاد قیمت"]}),
            (
                "create_activity",
                {
                    "activity_type": "follow_up",
                    "title": "پیگیری پیشنهاد قیمت {deal}",
                    "due_in_days": 2,
                    "assignee": "record_owner",
                },
            ),
        ],
    },
    "inactive_deal": {
        "name": "هشدار فروش بی‌فعالیت",
        "description": "اگر فروشی سه روز فعالیتی نداشت، به مدیر تیم هشدار داده می‌شود.",
        "steps": [
            ("trigger", {"event": "deal.inactive", "days": 3}),
            (
                "notify",
                {"recipient": "owner_manager", "title": "فروش «{deal}» سه روز بی‌فعالیت مانده است"},
            ),
        ],
    },
    "thank_you": {
        "name": "پیام تشکر پس از فروش",
        "description": "پس از ثبت «فروش انجام شد»، اگر مشتری اجازه داده باشد پیامک تشکر می‌گیرد.",
        "steps": [
            ("trigger", {"event": "deal.won"}),
            ("send_sms", {"text": "{name} عزیز، از اعتماد و خرید شما سپاسگزاریم."}),
        ],
    },
    "finance_follow_up": {
        "name": "پیگیری مالی پس از توافق نهایی",
        "description": (
            "با ورود فروش به «توافق نهایی»، پیگیری مالی به صف تیم مالی می‌رود و مشتری پیامک می‌گیرد."
        ),
        "steps": [
            ("trigger", {"event": "deal.stage_entered"}),
            ("condition", {"field": "stage", "operator": "in", "values": ["stage:توافق نهایی"]}),
            (
                "create_activity",
                {
                    "activity_type": "task",
                    "title": "پیگیری مالی {deal}",
                    "due_in_days": 1,
                    "assignee": "team",
                    "team_id": "team:finance",
                },
            ),
            (
                "send_sms",
                {"text": "{name} عزیز، کارشناس مالی برای هماهنگی پرداخت با شما تماس می‌گیرد."},
            ),
        ],
    },
}


def build_template(db: Session, key: str) -> dict[str, Any]:
    """Turns a template into a builder graph; stage names are resolved to ids here."""
    stages = {s.name: str(s.id) for s in db.scalars(select(Stage).where(Stage.is_active.is_(True)))}
    finance_team = db.scalar(
        select(Team.id)
        .where(Team.kind == TeamKind.FINANCE, Team.is_active.is_(True))
        .order_by(Team.name)
    )
    nodes, edges = [], []
    previous = None
    for index, (kind, config) in enumerate(TEMPLATES[key]["steps"]):
        config = dict(config)
        if kind == "condition":
            config["values"] = [stages.get(v.removeprefix("stage:"), "") for v in config["values"]]
            config["values"] = [v for v in config["values"] if v]
        if config.get("team_id") == "team:finance":
            # The first active finance team, if there is one; otherwise the block asks.
            config["team_id"] = str(finance_team) if finance_team else ""
        node_id = f"n{index + 1}"
        nodes.append(
            {"id": node_id, "kind": kind, "config": config, "position": {"x": 0, "y": index * 160}}
        )
        if previous:
            edges.append({"id": f"e{index}", "source": previous, "target": node_id})
        previous = node_id
    return {"nodes": nodes, "edges": edges}
