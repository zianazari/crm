"""Validating and compiling the builder graph (spec 4.6).

The builder stores nodes with positions and edges. Execution order comes only from the
edges, never from where blocks sit. Release 1 supports one start event followed by a
single linear path (no branches, no loops). Every problem is reported against the
block it concerns so the builder can mark it.
"""

from dataclasses import dataclass, field
from typing import Any

EVENTS = {
    "lead.created": "lead",
    "record.assigned": None,  # subject type comes from the trigger's entity_type
    "deal.stage_entered": "deal",
    "deal.won": "deal",
    "deal.lost": "deal",
    "activity.due": "activity",
    "deal.inactive": "deal",
}
ACTION_KINDS = {"create_activity", "notify", "send_sms", "send_email"}
STEP_KINDS = ACTION_KINDS | {"condition", "delay"}
CONDITION_FIELDS = {"source", "stage", "owner", "tag", "lead_status", "deal_status"}
ACTIVITY_TYPES = {"call", "meeting", "follow_up", "task"}
DELAY_UNITS = {"minutes": 60, "hours": 3600, "days": 86400}
MAX_DELAY_SECONDS = 90 * 86400


@dataclass
class Problem:
    node_id: str | None
    message: str


@dataclass
class Compiled:
    definition: dict[str, Any] | None
    problems: list[Problem] = field(default_factory=list)


def _text(config: dict[str, Any], key: str, low: int, high: int) -> bool:
    value = config.get(key)
    return isinstance(value, str) and low <= len(value.strip()) <= high


def _check_node(node: dict[str, Any]) -> list[str]:
    kind, config = node.get("kind"), node.get("config") or {}
    errors: list[str] = []
    if kind == "trigger":
        event = config.get("event")
        if event not in EVENTS:
            errors.append("رویداد شروع را انتخاب کنید.")
        if event == "record.assigned" and config.get("entity_type") not in {
            "lead",
            "customer",
            "deal",
        }:
            errors.append("نوع پرونده را برای «انتساب مسئول» انتخاب کنید.")
        if event == "deal.inactive":
            days = config.get("days")
            if not isinstance(days, int) or not 1 <= days <= 365:
                errors.append("تعداد روزهای بی‌فعالیتی باید بین ۱ و ۳۶۵ باشد.")
    elif kind == "condition":
        if config.get("field") not in CONDITION_FIELDS:
            errors.append("ویژگی شرط را انتخاب کنید.")
        if config.get("operator") not in {"in", "not_in"}:
            errors.append("نوع مقایسه شرط را انتخاب کنید.")
        values = config.get("values")
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(v, str) and v for v in values)
        ):
            errors.append("حداقل یک مقدار برای شرط انتخاب کنید.")
    elif kind == "create_activity":
        if config.get("activity_type") not in ACTIVITY_TYPES:
            errors.append("نوع فعالیت را انتخاب کنید.")
        if not _text(config, "title", 2, 200):
            errors.append("عنوان فعالیت لازم است.")
        due = config.get("due_in_days", 0)
        if not isinstance(due, int) or not 0 <= due <= 365:
            errors.append("موعد فعالیت باید بین ۰ و ۳۶۵ روز بعد باشد.")
        if config.get("assignee") not in {"record_owner", "user", "team"}:
            errors.append("مسئول انجام را انتخاب کنید.")
        if config.get("assignee") == "user" and not config.get("user_id"):
            errors.append("کاربر مسئول را انتخاب کنید.")
        if config.get("assignee") == "team" and not config.get("team_id"):
            errors.append("تیمی را که کار به صف آن می‌رود انتخاب کنید.")
    elif kind == "notify":
        if config.get("recipient") not in {"record_owner", "owner_manager", "user"}:
            errors.append("گیرنده اعلان را انتخاب کنید.")
        if config.get("recipient") == "user" and not config.get("user_id"):
            errors.append("کاربر گیرنده را انتخاب کنید.")
        if not _text(config, "title", 2, 200):
            errors.append("متن اعلان لازم است.")
    elif kind == "send_sms":
        if not _text(config, "text", 2, 500):
            errors.append("متن پیامک لازم است (حداکثر ۵۰۰ نویسه).")
    elif kind == "send_email":
        if not _text(config, "subject", 2, 200):
            errors.append("موضوع ایمیل لازم است.")
        if not _text(config, "text", 2, 5000):
            errors.append("متن ایمیل لازم است.")
    elif kind == "delay":
        amount, unit = config.get("amount"), config.get("unit")
        if unit not in DELAY_UNITS or not isinstance(amount, int) or amount < 1:
            errors.append("مدت تأخیر را وارد کنید.")
        elif amount * DELAY_UNITS[unit] > MAX_DELAY_SECONDS:
            errors.append("تأخیر حداکثر ۹۰ روز است.")
    else:
        errors.append("نوع بلوک نامعتبر است.")
    return errors


def subject_type(trigger: dict[str, Any]) -> str:
    event = trigger.get("event")
    return (
        str(trigger.get("entity_type"))
        if event == "record.assigned"
        else str(EVENTS.get(event or "", ""))
    )


def compile_graph(graph: dict[str, Any]) -> Compiled:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    problems: list[Problem] = []
    by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in by_id:
            problems.append(Problem(None, "شناسه بلوک‌ها تکراری یا خالی است."))
            continue
        by_id[node_id] = node
        for message in _check_node(node):
            problems.append(Problem(node_id, message))

    triggers = [n for n in by_id.values() if n.get("kind") == "trigger"]
    if not triggers:
        problems.append(Problem(None, "رویداد شروع وجود ندارد؛ یک بلوک «رویداد» اضافه کنید."))
        return Compiled(None, problems)
    for extra in triggers[1:]:
        problems.append(Problem(str(extra["id"]), "هر اتوماسیون فقط یک رویداد شروع دارد."))
    trigger = triggers[0]

    outgoing: dict[str, str] = {}
    incoming: dict[str, str] = {}
    for edge in edges:
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source not in by_id or target not in by_id or source == target:
            problems.append(Problem(source if source in by_id else None, "اتصال نامعتبر است."))
            continue
        if by_id[target].get("kind") == "trigger":
            problems.append(Problem(target, "به رویداد شروع نمی‌توان وصل شد."))
            continue
        if source in outgoing:
            problems.append(Problem(source, "در این نسخه هر بلوک فقط به یک بلوک بعدی وصل می‌شود."))
            continue
        if target in incoming:
            problems.append(Problem(target, "هر بلوک فقط یک ورودی دارد؛ مسیر باید خطی باشد."))
            continue
        outgoing[source], incoming[target] = target, source

    path: list[str] = []
    seen = {str(trigger["id"])}
    current = outgoing.get(str(trigger["id"]))
    while current is not None:
        if current in seen:
            problems.append(Problem(current, "مسیر دوری دارد؛ حلقه مجاز نیست."))
            break
        seen.add(current)
        path.append(current)
        current = outgoing.get(current)

    for node_id, node in by_id.items():
        if node_id not in seen and node.get("kind") != "trigger":
            problems.append(Problem(node_id, "این بلوک به مسیر وصل نیست."))

    kinds = [by_id[n].get("kind") for n in path]
    if not any(k in ACTION_KINDS for k in kinds):
        problems.append(Problem(str(trigger["id"]), "حداقل یک اقدام بعد از رویداد لازم است."))
    elif kinds and kinds[-1] in {"condition", "delay"}:
        problems.append(Problem(path[-1], "مسیر باید به یک اقدام ختم شود."))

    entity = subject_type(trigger.get("config") or {})
    for node_id in path:
        config = by_id[node_id].get("config") or {}
        if by_id[node_id].get("kind") == "condition":
            if config.get("field") in {"stage", "deal_status"} and entity not in {
                "deal",
                "activity",
            }:
                problems.append(
                    Problem(node_id, "شرط مرحله و وضعیت فروش فقط برای رویدادهای فروش معنا دارد.")
                )
            if config.get("field") == "lead_status" and entity not in {"lead", "activity"}:
                problems.append(
                    Problem(node_id, "شرط وضعیت مشتری احتمالی فقط برای مشتری احتمالی معنا دارد.")
                )

    if problems:
        return Compiled(None, problems)
    return Compiled(
        {
            "trigger": trigger.get("config") or {},
            "steps": [
                {"node_id": n, "kind": by_id[n]["kind"], "config": by_id[n].get("config") or {}}
                for n in path
            ],
        }
    )
