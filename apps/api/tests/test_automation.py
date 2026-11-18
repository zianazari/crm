"""Automation rules: builder validation, publishing and the engine (spec 4.6).

Covers acceptance criteria 9 (scope), 10 (repeated processing is harmless),
16 (stage events only on a real change) and 21 (activation is never retroactive).
The engine is driven directly with ``tick`` instead of a running worker.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.db.session import SessionLocal
from app.modules.activities.models import Activity
from app.modules.automation.engine import tick
from app.modules.automation.events import emit
from app.modules.automation.graph import compile_graph
from app.modules.automation.models import AutomationEvent, AutomationExecution
from app.modules.identity.models import User
from app.modules.messaging.models import OutboundMessage, OutboxEvent
from app.modules.notifications.models import Notification
from tests.conftest import Org, login_as
from tests.test_deals import make_customer, make_deal, stage_ids, win


@pytest.fixture(autouse=True)
def _clean_messages() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        db.execute(delete(OutboxEvent))
        db.execute(delete(OutboundMessage))
        db.commit()


def run(now: datetime | None = None) -> None:
    with SessionLocal() as db:
        assert tick(db, now)


def graph(*steps: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    nodes = [
        {"id": f"n{i}", "kind": kind, "config": config, "position": {"x": 0, "y": i * 160}}
        for i, (kind, config) in enumerate(steps)
    ]
    edges = [
        {"id": f"e{i}", "source": f"n{i - 1}", "target": f"n{i}"} for i in range(1, len(steps))
    ]
    return {"nodes": nodes, "edges": edges}


def rule_with(client: TestClient, g: dict[str, Any], **draft: Any) -> dict[str, Any]:
    rule = client.post("/automations", json={"name": "قانون آزمایشی"}).json()
    r = client.put(
        f"/automations/{rule['id']}/draft", json={"name": "قانون آزمایشی", "graph": g, **draft}
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def publish(client: TestClient, rule_id: str) -> dict[str, Any]:
    r = client.post(f"/automations/{rule_id}/publish")
    assert r.status_code == 200, r.text
    return dict(r.json())


def from_template(client: TestClient, key: str) -> dict[str, Any]:
    r = client.post("/automations", json={"name": "از قالب", "template": key})
    assert r.status_code == 201, r.text
    return dict(r.json())


def executions(rule_id: str) -> list[AutomationExecution]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AutomationExecution)
                .where(AutomationExecution.rule_id == uuid.UUID(rule_id))
                .order_by(AutomationExecution.created_at)
            ).unique()
        )


def delayed(rule_id: str) -> dict[uuid.UUID, AutomationExecution]:
    """The runs that got as far as a delay, by record."""
    return {
        e.subject_id: e
        for e in executions(rule_id)
        if any(entry["type"] == "delay" for entry in e.log)
    }


def activities_titled(text: str) -> list[Activity]:
    with SessionLocal() as db:
        return list(db.scalars(select(Activity).where(Activity.title.contains(text))).unique())


NOTIFY = ("notify", {"recipient": "record_owner", "title": "اعلان آزمایشی"})


# -- builder validation ----------------------------------------------------------


def test_compile_reports_problems_per_block() -> None:
    assert [p.message for p in compile_graph({"nodes": [], "edges": []}).problems] == [
        "رویداد شروع وجود ندارد؛ یک بلوک «رویداد» اضافه کنید."
    ]
    only_trigger = compile_graph(graph(("trigger", {"event": "lead.created"})))
    assert [p.node_id for p in only_trigger.problems] == ["n0"]

    ends_in_condition = compile_graph(
        graph(
            ("trigger", {"event": "lead.created"}),
            NOTIFY,
            ("condition", {"field": "source", "operator": "in", "values": ["x"]}),
        )
    )
    assert any(p.node_id == "n2" for p in ends_in_condition.problems)

    branched = graph(("trigger", {"event": "lead.created"}), NOTIFY, NOTIFY)
    branched["edges"] = [
        {"id": "a", "source": "n0", "target": "n1"},
        {"id": "b", "source": "n0", "target": "n2"},
    ]
    problems = compile_graph(branched).problems
    assert {p.node_id for p in problems} == {"n0", "n2"}  # second exit + orphaned block

    wrong_entity = compile_graph(
        graph(
            ("trigger", {"event": "lead.created"}),
            ("condition", {"field": "stage", "operator": "in", "values": ["x"]}),
            NOTIFY,
        )
    )
    assert [p.node_id for p in wrong_entity.problems] == ["n1"]

    ok = compile_graph(graph(("trigger", {"event": "lead.created"}), NOTIFY))
    assert ok.problems == [] and ok.definition is not None
    assert [s["node_id"] for s in ok.definition["steps"]] == ["n1"]


def test_execution_order_comes_from_edges_not_positions() -> None:
    g = graph(("trigger", {"event": "lead.created"}), NOTIFY, ("send_sms", {"text": "سلام {name}"}))
    g["nodes"][1]["position"], g["nodes"][2]["position"] = {"x": 0, "y": 900}, {"x": 0, "y": 10}
    definition = compile_graph(g).definition
    assert definition is not None
    assert [s["kind"] for s in definition["steps"]] == ["notify", "send_sms"]


def test_publish_with_problems_is_rejected_and_keeps_rule_inactive(org: Org) -> None:
    manager = login_as(org.manager.id)
    rule = rule_with(manager, graph(("trigger", {"event": "lead.created"})))
    assert rule["problems"] and rule["status"] == "draft"
    r = manager.post(f"/automations/{rule['id']}/publish")
    assert r.status_code == 422
    assert r.json()["detail"]["problems"][0]["node_id"] == "n0"
    assert manager.get(f"/automations/{rule['id']}").json()["status"] == "draft"


def test_publish_rejects_users_outside_scope(org: Org) -> None:
    manager = login_as(org.manager.id)
    notify_other = (
        "notify",
        {"recipient": "user", "user_id": str(org.other_rep.id), "title": "x y"},
    )
    rule = rule_with(manager, graph(("trigger", {"event": "lead.created"}), notify_other))
    r = manager.post(f"/automations/{rule['id']}/publish")
    assert r.status_code == 422
    assert r.json()["detail"]["problems"] == [
        {"node_id": "n1", "message": "این کاربر خارج از دامنه شما است."}
    ]


def test_templates_and_versions(org: Org) -> None:
    manager = login_as(org.manager.id)
    keys = [t["key"] for t in manager.get("/automations/templates").json()]
    assert keys == [
        "first_call",
        "due_reminder",
        "proposal_follow_up",
        "inactive_deal",
        "thank_you",
        "finance_follow_up",
    ]
    for key in keys[:-1]:
        rule = from_template(manager, key)
        assert rule["problems"] == [], (key, rule["problems"])
    # The finance template needs the finance user chosen before it can be published.
    finance = from_template(manager, "finance_follow_up")
    assert [p["message"] for p in finance["problems"]] == ["کاربر مسئول را انتخاب کنید."]

    proposal = from_template(manager, "proposal_follow_up")
    condition = proposal["draft"]["nodes"][1]["config"]
    assert condition["values"] == [stage_ids()[2]]
    published = publish(manager, proposal["id"])
    assert published["active_version"]["number"] == 1 and not published["unpublished_changes"]
    assert publish(manager, proposal["id"])["active_version"]["number"] == 2
    versions = manager.get(f"/automations/{proposal['id']}/versions").json()
    assert [v["number"] for v in versions] == [2, 1]


# -- access ------------------------------------------------------------------------


def test_only_managers_and_admins_and_only_own_rules(org: Org) -> None:
    assert login_as(org.rep1.id).get("/automations").status_code == 403
    rule = from_template(login_as(org.manager.id), "first_call")
    assert login_as(org.other_manager.id).get(f"/automations/{rule['id']}").status_code == 404
    assert login_as(org.other_manager.id).get("/automations").json() == []
    assert [r["id"] for r in login_as(org.admin.id).get("/automations").json()] == [rule["id"]]


def test_manager_rule_only_touches_own_team(org: Org) -> None:
    """Criterion 9: a rule never reaches records outside its author's scope."""
    manager = login_as(org.manager.id)
    rule = from_template(manager, "first_call")
    publish(manager, rule["id"])
    login_as(org.rep1.id).post(
        "/leads", json={"full_name": "سرنخ تیم الف", "mobile": "09121110001"}
    )
    login_as(org.other_rep.id).post(
        "/leads", json={"full_name": "سرنخ تیم ب", "mobile": "09121110002"}
    )
    run()
    runs = {e.status.value: e for e in executions(rule["id"])}
    assert set(runs) == {"completed", "skipped"}
    assert runs["skipped"].error == "پرونده خارج از دامنه سازنده قانون است."
    created = activities_titled("اولین تماس")
    assert [(a.title, a.owner_id) for a in created] == [("اولین تماس با سرنخ تیم الف", org.rep1.id)]


# -- engine ------------------------------------------------------------------------


def test_activation_is_not_retroactive_and_reprocessing_is_harmless(org: Org) -> None:
    """Criteria 21 and 10."""
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    rep.post("/leads", json={"full_name": "قبل از فعال‌سازی", "mobile": "09121110003"})
    rule = from_template(manager, "first_call")
    publish(manager, rule["id"])
    rep.post("/leads", json={"full_name": "بعد از فعال‌سازی", "mobile": "09121110004"})
    run()
    run()
    assert [a.title for a in activities_titled("اولین تماس")] == ["اولین تماس با بعد از فعال‌سازی"]

    # Processing the same events again (e.g. after a crash) changes nothing.
    with SessionLocal() as db:
        db.execute(update(AutomationEvent).values(processed_at=None))
        db.commit()
    run()
    assert len(executions(rule["id"])) == 1
    assert len(activities_titled("اولین تماس")) == 1
    with SessionLocal() as db:
        assigned = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == org.rep1.id)
        )
    assert assigned == 1


def test_stage_event_only_on_real_change(org: Org) -> None:
    """Criterion 16, with the proposal follow-up template."""
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    rule = from_template(manager, "proposal_follow_up")
    publish(manager, rule["id"])
    deal = make_deal(rep, make_customer(rep))
    stages = stage_ids()
    same = rep.post(f"/deals/{deal['id']}/move", json={"stage_id": stages[0], "version": 1}).json()
    assert same["version"] == 1
    moved = rep.post(f"/deals/{deal['id']}/move", json={"stage_id": stages[2], "version": 1}).json()
    run()
    with SessionLocal() as db:
        types = list(db.scalars(select(AutomationEvent.type).order_by(AutomationEvent.created_at)))
    assert types == ["deal.stage_entered", "deal.stage_entered"]  # created + one real move
    runs = executions(rule["id"])
    assert [e.status.value for e in runs] == ["skipped", "completed"]  # first stage: not met
    follow_ups = activities_titled("پیگیری پیشنهاد قیمت")
    assert len(follow_ups) == 1 and follow_ups[0].owner_id == org.rep1.id
    assert moved["version"] == 2


def test_delay_rechecks_conditions_and_pause_cancels_waiting(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    stages = stage_ids()
    g = graph(
        ("trigger", {"event": "deal.stage_entered"}),
        ("condition", {"field": "stage", "operator": "in", "values": [stages[1]]}),
        ("delay", {"amount": 1, "unit": "hours"}),
        NOTIFY,
    )
    rule = rule_with(manager, g)
    publish(manager, rule["id"])
    first = make_deal(rep, make_customer(rep), title="فروش اول")
    second = make_deal(rep, make_customer(rep, "شرکت دوم", "09122222222"), title="فروش دوم")
    rep.post(f"/deals/{first['id']}/move", json={"stage_id": stages[1], "version": 1})
    rep.post(f"/deals/{second['id']}/move", json={"stage_id": stages[1], "version": 1})
    run()
    waiting = [e for e in executions(rule["id"]) if e.status.value == "waiting"]
    assert len(waiting) == 2

    # The first deal leaves the stage during the delay: the run must not continue.
    rep.post(f"/deals/{first['id']}/move", json={"stage_id": stages[3], "version": 2})
    run(datetime.now(UTC) + timedelta(minutes=30))
    assert sum(e.status.value == "waiting" for e in executions(rule["id"])) == 2  # not yet due
    run(datetime.now(UTC) + timedelta(hours=2))
    by_subject = delayed(rule["id"])
    assert by_subject[uuid.UUID(first["id"])].status.value == "skipped"
    assert by_subject[uuid.UUID(second["id"])].status.value == "completed"

    # A new waiting run is canceled when the rule is paused.
    third = make_deal(rep, make_customer(rep, "شرکت سوم", "09123333333"), title="فروش سوم")
    rep.post(f"/deals/{third['id']}/move", json={"stage_id": stages[1], "version": 1})
    run()
    paused = manager.post(f"/automations/{rule['id']}/pause").json()
    assert paused["status"] == "paused"
    assert delayed(rule["id"])[uuid.UUID(third["id"])].status.value == "canceled"
    run(datetime.now(UTC) + timedelta(hours=2))
    with SessionLocal() as db:
        notified = db.scalars(select(Notification.title).where(Notification.user_id == org.rep1.id))
        assert list(notified).count("اعلان آزمایشی") == 1


def test_messages_respect_consent_at_sending_time(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    rule = from_template(manager, "thank_you")
    publish(manager, rule["id"])
    silent = make_deal(rep, make_customer(rep, "بدون اجازه", "09124444444"))
    customer = rep.post(
        "/customers",
        json={"full_name": "با اجازه", "mobile": "09125555555", "sms_consent": True},
    ).json()
    assert customer["sms_consent"] is True and customer["consent_updated_at"]
    allowed = make_deal(rep, customer["id"])
    win(rep, silent)
    win(rep, allowed)
    run()
    logs = {e.subject_id: e.log[-1] for e in executions(rule["id"])}
    assert logs[uuid.UUID(silent["id"])]["result"] == "skipped"
    assert logs[uuid.UUID(allowed["id"])]["result"] == "done"
    with SessionLocal() as db:
        sent = list(db.scalars(select(OutboundMessage)))
    assert [(m.recipient, m.body) for m in sent] == [
        ("+989125555555", "با اجازه عزیز، از اعتماد و خرید شما سپاسگزاریم.")
    ]


def test_failed_action_stops_run_and_tells_author(org: Org) -> None:
    manager = login_as(org.manager.id)
    task = {
        "activity_type": "task",
        "title": "کار {name}",
        "due_in_days": 1,
        "assignee": "user",
        "user_id": str(org.rep2.id),
    }
    rule = rule_with(
        manager, graph(("trigger", {"event": "lead.created"}), ("create_activity", task), NOTIFY)
    )
    publish(manager, rule["id"])
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == org.rep2.id).values(is_active=False))
        db.commit()
    login_as(org.rep1.id).post("/leads", json={"full_name": "سرنخ", "mobile": "09121110005"})
    run()
    [execution] = executions(rule["id"])
    assert execution.status.value == "failed" and execution.error
    assert [e["result"] for e in execution.log] == ["failed"]  # the notify step never ran
    assert activities_titled("کار سرنخ") == []
    with SessionLocal() as db:
        alert = db.scalar(select(Notification).where(Notification.user_id == org.manager.id))
    assert alert is not None and alert.link == f"/automations/{rule['id']}"
    summary = manager.get("/automations").json()[0]
    assert summary["runs_last_30_days"] == 1 and summary["failures_last_30_days"] == 1
    page = manager.get(f"/automations/{rule['id']}/executions").json()
    assert page["total"] == 1 and page["items"][0]["subject_name"] == "سرنخ"


def test_inactive_deal_alerts_team_manager_once(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep), title="فروش ساکت")
    rule = from_template(manager, "inactive_deal")
    publish(manager, rule["id"])
    run()
    assert executions(rule["id"]) == []  # not inactive yet
    later = datetime.now(UTC) + timedelta(days=4)
    run(later)
    run(later + timedelta(minutes=1))
    [execution] = executions(rule["id"])
    assert execution.status.value == "completed" and execution.subject_id == uuid.UUID(deal["id"])
    with SessionLocal() as db:
        titles = list(
            db.scalars(select(Notification.title).where(Notification.user_id == org.manager.id))
        )
    assert titles == ["فروش «فروش ساکت» سه روز بی‌فعالیت مانده است"]


def test_once_per_record_and_loop_depth(org: Org) -> None:
    manager = login_as(org.manager.id)
    g = graph(("trigger", {"event": "record.assigned", "entity_type": "lead"}), NOTIFY)
    rule = rule_with(manager, g, repeat_policy="once_per_record")
    publish(manager, rule["id"])
    lead = (
        login_as(org.rep1.id)
        .post("/leads", json={"full_name": "سرنخ", "mobile": "09121110006"})
        .json()
    )
    with SessionLocal() as db:
        for i in range(2):
            emit(db, "record.assigned", "lead", uuid.UUID(lead["id"]), {"n": i})
        emit(db, "record.assigned", "lead", uuid.UUID(lead["id"]), {"n": 9}, depth=4)
        db.commit()
    run()
    runs = executions(rule["id"])
    assert [e.status.value for e in runs] == ["completed", "skipped", "skipped"]
    assert "قبلاً" in (runs[1].error or "") and "حلقه" in (runs[2].error or "")


def test_dry_run_creates_nothing(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    g = graph(
        ("trigger", {"event": "lead.created"}),
        ("delay", {"amount": 2, "unit": "hours"}),
        (
            "create_activity",
            {"activity_type": "call", "title": "تماس با {name}", "assignee": "record_owner"},
        ),
        ("send_sms", {"text": "سلام {name}"}),
    )
    rule = rule_with(manager, g)
    lead = rep.post("/leads", json={"full_name": "مینا", "mobile": "09121110007"}).json()
    result = manager.post(f"/automations/{rule['id']}/test", json={"subject_id": lead["id"]}).json()
    assert result["subject"] == "مینا"
    assert [s["outcome"] for s in result["steps"]] == ["wait", "would_run", "would_skip"]
    assert result["steps"][1]["detail"] == "فعالیت «تماس با مینا» ساخته می‌شود."
    assert activities_titled("تماس با مینا") == []
    other = login_as(org.other_rep.id).post(
        "/leads", json={"full_name": "غریبه", "mobile": "09121110008"}
    )
    r = manager.post(f"/automations/{rule['id']}/test", json={"subject_id": other.json()["id"]})
    assert r.status_code == 404


def test_only_one_tick_runs_at_a_time(org: Org) -> None:
    from sqlalchemy import text

    from app.db.session import engine
    from app.modules.automation.engine import ADVISORY_LOCK

    with engine.connect() as other:
        assert other.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK})
        with SessionLocal() as db:
            assert tick(db) is False
        other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK})
    for _ in range(3):  # the lock is released after every pass
        run()
