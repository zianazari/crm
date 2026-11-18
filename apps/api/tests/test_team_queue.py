"""Team work queue for the finance team (spec 4.6, section 5; criterion 16).

A finance step queues work for a team; one member claims it (atomically) or the team
manager assigns it. Finance members see their activities, the queue and the deal
details the task needs — not the sales lists.
"""

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.db.session import SessionLocal
from app.modules.activities.models import Activity, TeamTask
from app.modules.automation.models import AutomationExecution
from app.modules.identity.models import Role, Team, TeamKind, User
from app.modules.messaging.models import OutboundMessage, OutboxEvent
from app.modules.notifications.models import Notification
from tests.conftest import Org, login_as
from tests.test_automation import publish, run
from tests.test_deals import make_customer, make_deal, stage_ids


@dataclass
class Finance:
    team: Team
    manager: User
    member1: User
    member2: User


@pytest.fixture
def finance(org: Org) -> Finance:
    with SessionLocal() as db:
        team = Team(name="مالی", kind=TeamKind.FINANCE)
        db.add(team)
        db.flush()
        users = [
            User(full_name="مدیر مالی", mobile="+989100000010", role=Role.SALES_MANAGER, team=team),
            User(
                full_name="کارشناس مالی ۱", mobile="+989100000011", role=Role.SALES_REP, team=team
            ),
            User(
                full_name="کارشناس مالی ۲", mobile="+989100000012", role=Role.SALES_REP, team=team
            ),
        ]
        db.add_all(users)
        db.flush()
        team.manager_id = users[0].id
        db.commit()
        return Finance(team, *users)


@pytest.fixture(autouse=True)
def _clean_messages() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        db.execute(delete(OutboxEvent))
        db.execute(delete(OutboundMessage))
        db.commit()


def queue_one(org: Org, title: str = "پیاده‌سازی CRM") -> tuple[dict[str, Any], dict[str, Any]]:
    """Publishes the finance template and moves a deal into «توافق نهایی»."""
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    rule = manager.post(
        "/automations", json={"name": "پیگیری مالی", "template": "finance_follow_up"}
    ).json()
    assert rule["problems"] == [], rule["problems"]
    publish(manager, rule["id"])
    deal = make_deal(rep, make_customer(rep), title=title)
    rep.post(f"/deals/{deal['id']}/move", json={"stage_id": stage_ids()[3], "version": 1})
    run()
    return rule, deal


def open_tasks(client: TestClient) -> list[dict[str, Any]]:
    r = client.get("/team-tasks")
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


def test_finance_step_queues_work_and_tells_the_team(org: Org, finance: Finance) -> None:
    _, deal = queue_one(org)
    # Recording the same stage again is not a new entry: nothing more is queued.
    login_as(org.rep1.id).post(
        f"/deals/{deal['id']}/move", json={"stage_id": stage_ids()[3], "version": 2}
    )
    run()
    [task] = open_tasks(login_as(finance.member1.id))
    assert task["team"]["name"] == "مالی" and task["status"] == "open"
    assert task["title"] == "پیگیری مالی پیاده‌سازی CRM" and task["can_claim"]
    assert task["deal"]["id"] == deal["id"]
    ctx = task["context"]
    assert ctx["mobile"] == "+989121111111" and ctx["amount"] == 450_000_000
    assert ctx["paid"] == 0 and ctx["balance"] == 450_000_000 and ctx["stage"] == "توافق نهایی"
    with SessionLocal() as db:
        assert db.scalars(select(Activity).where(Activity.team_task_id.is_not(None))).all() == []
        told = set(db.scalars(select(Notification.user_id).where(Notification.kind == "team_task")))
    assert told == {finance.manager.id, finance.member1.id, finance.member2.id}
    # The manager sees it with assignment rights; sales users do not see the queue.
    assert open_tasks(login_as(finance.manager.id))[0]["can_manage"]
    assert open_tasks(login_as(org.rep1.id)) == []
    assert open_tasks(login_as(org.manager.id)) == []
    assert len(open_tasks(login_as(org.admin.id))) == 1


def test_claim_is_atomic_and_creates_the_members_activity(org: Org, finance: Finance) -> None:
    queue_one(org)
    task_id = open_tasks(login_as(finance.member1.id))[0]["id"]
    clients = [login_as(finance.member1.id), login_as(finance.member2.id)]
    barrier = threading.Barrier(2)
    codes: list[int] = []

    def claim(client: TestClient) -> None:
        barrier.wait()
        codes.append(client.post(f"/team-tasks/{task_id}/claim").status_code)

    threads = [threading.Thread(target=claim, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 409]
    with SessionLocal() as db:
        [activity] = db.scalars(select(Activity).where(Activity.team_task_id.is_not(None))).all()
        task = db.get(TeamTask, uuid.UUID(task_id))
        assert task is not None and task.status.value == "assigned"
        assert activity.owner_id == task.assigned_to_id
    # The new owner sees the task context behind their activity; the queue is empty.
    owner = login_as(activity.owner_id)
    mine = owner.get("/activities", params={"mine": True}).json()["items"]
    assert [a["team_task_id"] for a in mine] == [task_id]
    assert owner.get(f"/team-tasks/{task_id}").json()["context"]["amount"] == 450_000_000
    assert open_tasks(owner) == []
    assert login_as(org.rep2.id).post(f"/team-tasks/{task_id}/claim").status_code == 404


def test_manager_assigns_and_cancels(org: Org, finance: Finance) -> None:
    queue_one(org, "فروش اول")
    rep = login_as(org.rep1.id)
    other = make_deal(rep, make_customer(rep, "شرکت دوم", "09122222222"), title="فروش دوم")
    rep.post(f"/deals/{other['id']}/move", json={"stage_id": stage_ids()[3], "version": 1})
    run()
    fm = login_as(finance.manager.id)
    first, second = open_tasks(fm)
    members = fm.get(f"/team-tasks/{first['id']}/members").json()
    assert {m["id"] for m in members} == {
        str(finance.manager.id),
        str(finance.member1.id),
        str(finance.member2.id),
    }
    # Only members of the team can receive it, and only its manager can assign.
    outsider = fm.post(f"/team-tasks/{first['id']}/assign", json={"user_id": str(org.rep1.id)})
    assert outsider.status_code == 422
    assert (
        login_as(finance.member1.id)
        .post(f"/team-tasks/{first['id']}/assign", json={"user_id": str(finance.member2.id)})
        .status_code
        == 403
    )
    r = fm.post(f"/team-tasks/{first['id']}/assign", json={"user_id": str(finance.member2.id)})
    assert r.status_code == 200 and r.json()["owner"]["id"] == str(finance.member2.id)
    with SessionLocal() as db:
        kinds = db.scalars(
            select(Notification.kind).where(Notification.user_id == finance.member2.id)
        ).all()
    assert "activity_assigned" in [k.value for k in kinds]

    canceled = fm.post(f"/team-tasks/{second['id']}/cancel", json={"reason": "تسویه شده است"})
    assert canceled.status_code == 200 and canceled.json()["status"] == "canceled"
    assert open_tasks(fm) == []
    assert fm.post(f"/team-tasks/{second['id']}/claim").status_code == 409


def test_finance_members_do_not_get_sales_views(org: Org, finance: Finance) -> None:
    """Criterion 16: a finance member sees only what their tasks need."""
    _, deal = queue_one(org)
    member = login_as(finance.member1.id)
    for path in (
        "/leads",
        "/customers",
        "/organizations",
        "/deals",
        "/deals/board",
        f"/deals/{deal['id']}",
        f"/deals/{deal['id']}/payments",
        "/reports/summary",
        f"/timeline?deal_id={deal['id']}",
        "/duplicates?mobile=09121111111",
    ):
        assert member.get(path).status_code == 403, path
    assert member.get("/activities").status_code == 200
    me = member.get("/auth/me").json()
    assert me["finance_member"] is True and me["queue_team_ids"] == [str(finance.team.id)]
    sales = login_as(org.rep1.id).get("/auth/me").json()
    assert sales["finance_member"] is False and sales["queue_team_ids"] == []
    # The finance manager is a manager, not a finance member.
    assert login_as(finance.manager.id).get("/deals").status_code == 200


def test_inactive_or_empty_team_stops_the_run_and_tells_the_author(
    org: Org, finance: Finance
) -> None:
    manager = login_as(org.manager.id)
    rule = manager.post(
        "/automations", json={"name": "پیگیری مالی", "template": "finance_follow_up"}
    ).json()
    publish(manager, rule["id"])
    with SessionLocal() as db:
        db.execute(update(User).where(User.team_id == finance.team.id).values(is_active=False))
        db.commit()
    rep = login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep))
    rep.post(f"/deals/{deal['id']}/move", json={"stage_id": stage_ids()[3], "version": 1})
    run()
    with SessionLocal() as db:
        failed = db.scalars(
            select(AutomationExecution).where(AutomationExecution.status == "failed")
        ).all()
        assert len(failed) == 1 and "عضو فعالی ندارد" in (failed[0].error or "")
        assert db.scalars(select(TeamTask)).all() == []
        alert = db.scalar(select(Notification).where(Notification.user_id == org.manager.id))
    assert alert is not None and alert.link == f"/automations/{rule['id']}"


def test_publish_requires_an_active_finance_team(org: Org, finance: Finance) -> None:
    manager = login_as(org.manager.id)
    rule = manager.post(
        "/automations", json={"name": "پیگیری مالی", "template": "finance_follow_up"}
    ).json()
    with SessionLocal() as db:
        sales_team = db.scalar(select(Team.id).where(Team.name == "فروش الف"))
    graph = rule["draft"]
    graph["nodes"][2]["config"]["team_id"] = str(sales_team)
    manager.put(f"/automations/{rule['id']}/draft", json={"name": "پیگیری مالی", "graph": graph})
    r = manager.post(f"/automations/{rule['id']}/publish")
    assert r.status_code == 422
    assert r.json()["detail"]["problems"][0]["message"] == (
        "فقط تیم‌های عملیاتی (مالی) فعال صف کار دارند."
    )
    targets = manager.get("/team-tasks/targets").json()
    assert targets == [{"id": str(finance.team.id), "name": "مالی"}]
    assert login_as(org.rep1.id).get("/team-tasks/targets").status_code == 403


def test_dry_run_names_the_queue(org: Org, finance: Finance) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    rule = manager.post(
        "/automations", json={"name": "پیگیری مالی", "template": "finance_follow_up"}
    ).json()
    deal = make_deal(rep, make_customer(rep))
    rep.post(f"/deals/{deal['id']}/move", json={"stage_id": stage_ids()[3], "version": 1})
    result = manager.post(f"/automations/{rule['id']}/test", json={"subject_id": deal["id"]}).json()
    assert "به صف تیم «مالی» می‌رود" in result["steps"][1]["detail"]
