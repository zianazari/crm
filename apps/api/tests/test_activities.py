"""Activities, calendar, workload, notes and timeline (spec 4.2; criteria 6, 14, 15, 20)."""

import threading
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.activities.models import ActivityEvent
from app.modules.activities.service import today
from app.modules.crm.models import Lead
from app.modules.sales.models import Deal
from tests.conftest import Org, login_as
from tests.test_deals import make_customer, make_deal


def iso(d: date) -> str:
    return d.isoformat()


def create(client: TestClient, **fields: Any) -> dict[str, Any]:
    body = {"type": "call", "title": "تماس پیگیری", "due_date": iso(today()), **fields}
    r = client.post("/activities", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


# -- creating & linking ------------------------------------------------------


def test_activity_on_deal_links_customer_and_shows_on_board(org: Org) -> None:
    rep = login_as(org.rep1.id)
    customer = make_customer(rep)
    deal = make_deal(rep, customer)
    make_deal(rep, customer, title="بدون پیگیری")
    activity = create(rep, deal_id=deal["id"], start_time="10:30", duration_minutes=30)

    assert activity["customer"]["id"] == customer
    assert activity["deal"]["name"] == "پیاده‌سازی CRM"
    cards = {d["title"]: d for d in rep.get("/deals/board").json()["columns"][0]["deals"]}
    assert cards["پیاده‌سازی CRM"]["next_activity"]["id"] == activity["id"]
    assert cards["بدون پیگیری"]["next_activity"] is None


def test_rep_cannot_plan_on_others_records_or_for_others(org: Org) -> None:
    rep2 = login_as(org.rep2.id)
    others_deal = make_deal(rep2, make_customer(rep2))
    rep1 = login_as(org.rep1.id)
    r = rep1.post(
        "/activities",
        json={
            "type": "call",
            "title": "تماس",
            "due_date": iso(today()),
            "deal_id": others_deal["id"],
        },
    )
    assert r.status_code == 403
    r = rep1.post(
        "/activities",
        json={
            "type": "task",
            "title": "کار",
            "due_date": iso(today()),
            "owner_id": str(org.rep2.id),
        },
    )
    assert r.status_code == 403


def test_manager_assigns_to_team_member_who_then_sees_it(org: Org) -> None:
    manager = login_as(org.manager.id)
    activity = create(manager, type="task", title="پیگیری مالی", owner_id=str(org.rep1.id))
    items = login_as(org.rep1.id).get("/activities", params={"range": "today"}).json()["items"]
    assert [a["id"] for a in items] == [activity["id"]]
    assert login_as(org.rep2.id).get(f"/activities/{activity['id']}").status_code == 403


def test_duration_needs_a_start_time(org: Org) -> None:
    r = login_as(org.rep1.id).post(
        "/activities",
        json={"type": "meeting", "title": "جلسه", "due_date": iso(today()), "duration_minutes": 30},
    )
    assert r.status_code == 422


# -- lists ---------------------------------------------------------------------


def test_ranges_and_separation_of_done(org: Org) -> None:
    rep = login_as(org.rep1.id)
    on = today()
    late = create(rep, title="معوق", due_date=iso(on - timedelta(days=2)))
    now = create(rep, title="امروز")
    tomorrow = create(rep, title="فردا", due_date=iso(on + timedelta(days=1)))
    done = create(rep, title="انجام‌شده")
    rep.post(f"/activities/{done['id']}/complete", json={"outcome": "انجام شد", "version": 1})

    def titles(**params: Any) -> list[str]:
        return [a["title"] for a in rep.get("/activities", params=params).json()["items"]]

    assert titles(range="overdue") == ["معوق"]
    assert titles(range="today") == ["امروز"]
    assert titles(range="tomorrow") == ["فردا"]
    assert titles() == ["معوق", "امروز", "فردا"]
    assert titles(status="done") == ["انجام‌شده"]
    assert rep.get(f"/activities/{late['id']}").json()["overdue"] is True
    assert rep.get(f"/activities/{now['id']}").json()["overdue"] is False
    assert tomorrow["status"] == "pending"


def test_calendar_excludes_cancelled(org: Org) -> None:
    rep = login_as(org.rep1.id)
    on = today()
    create(rep, title="بدون ساعت")
    create(rep, title="ساعت‌دار", start_time="09:00", duration_minutes=60)
    cancelled = create(rep, title="لغو")
    rep.post(f"/activities/{cancelled['id']}/cancel", json={"reason": "منتفی شد", "version": 1})
    items = rep.get(
        "/activities/calendar", params={"date_from": iso(on), "date_to": iso(on)}
    ).json()
    assert sorted(a["title"] for a in items) == ["بدون ساعت", "ساعت‌دار"]
    timed = next(a for a in items if a["title"] == "ساعت‌دار")
    assert timed["start_at"] is not None


# -- completing, postponing, cancelling (criteria 6, 15, 20) -------------------


def test_complete_records_result_and_updates_files(org: Org) -> None:
    rep = login_as(org.rep1.id)
    lead = rep.post("/leads", json={"full_name": "علی رضایی", "mobile": "09121111111"}).json()
    deal = make_deal(rep, make_customer(rep, mobile="09122222222"))
    on_lead = create(rep, lead_id=lead["id"])
    on_deal = create(rep, deal_id=deal["id"], type="meeting")

    for activity in (on_lead, on_deal):
        r = rep.post(
            f"/activities/{activity['id']}/complete",
            json={"outcome": "قرار جلسه گذاشته شد", "version": 1},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "done" and body["completed_by"]["id"] == str(org.rep1.id)
        # Planned time and actual completion time are both kept (criterion 20).
        assert body["due_date"] == iso(today()) and body["completed_at"] is not None

    with SessionLocal() as db:
        assert db.get(Lead, lead["id"]).last_contacted_at is not None  # type: ignore[union-attr]
        assert db.get(Deal, deal["id"]).last_activity_at is not None  # type: ignore[union-attr]


def test_completing_twice_is_rejected_even_concurrently(org: Org) -> None:
    rep = login_as(org.rep1.id)
    activity = create(rep)
    results: list[int] = []

    def complete() -> None:
        r = login_as(org.rep1.id).post(
            f"/activities/{activity['id']}/complete", json={"outcome": "انجام شد", "version": 1}
        )
        results.append(r.status_code)

    threads = [threading.Thread(target=complete) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 409]
    with SessionLocal() as db:
        kinds = db.scalars(
            select(ActivityEvent.kind).where(ActivityEvent.activity_id == activity["id"])
        ).all()
        assert list(kinds).count("completed") == 1


def test_postpone_and_reschedule_are_tracked(org: Org) -> None:
    rep = login_as(org.rep1.id)
    activity = create(rep, due_date=iso(today() - timedelta(days=1)))
    new_day = today() + timedelta(days=3)
    r = rep.post(
        f"/activities/{activity['id']}/postpone",
        json={
            "due_date": iso(new_day),
            "start_time": "14:00",
            "version": 1,
            "reason": "مشتری در سفر",
        },
    )
    assert r.status_code == 200 and r.json()["overdue"] is False
    r = rep.patch(
        f"/activities/{activity['id']}",
        json={
            "owner_id": str(org.rep1.id),
            "due_date": iso(new_day + timedelta(days=1)),
            "version": 2,
        },
    )
    assert r.status_code == 200
    events = rep.get(f"/activities/{activity['id']}/events").json()
    assert [e["kind"] for e in events] == ["created", "postponed", "rescheduled"]
    assert events[1]["details"]["reason"] == "مشتری در سفر"


def test_cancel_needs_reason_and_closed_activity_is_read_only(org: Org) -> None:
    rep = login_as(org.rep1.id)
    activity = create(rep)
    assert rep.post(f"/activities/{activity['id']}/cancel", json={"version": 1}).status_code == 422
    assert (
        rep.post(
            f"/activities/{activity['id']}/cancel", json={"reason": "منتفی شد", "version": 1}
        ).status_code
        == 200
    )
    r = rep.patch(f"/activities/{activity['id']}", json={"title": "جدید", "version": 2})
    assert r.status_code == 409


def test_stale_version_is_rejected(org: Org) -> None:
    rep = login_as(org.rep1.id)
    activity = create(rep)
    rep.patch(f"/activities/{activity['id']}", json={"title": "عنوان تازه", "version": 1})
    r = rep.post(f"/activities/{activity['id']}/complete", json={"outcome": "x", "version": 1})
    assert r.status_code == 409


# -- workload & schedules -------------------------------------------------------


def test_workload_counts_and_overlaps(org: Org) -> None:
    rep = login_as(org.rep1.id)
    a = create(rep, title="جلسه ۱", type="meeting", start_time="10:00", duration_minutes=60)
    b = create(rep, title="جلسه ۲", type="meeting", start_time="10:30", duration_minutes=30)
    create(rep, title="بعدازظهر", start_time="15:00", duration_minutes=15)
    create(rep, title="بدون ساعت")
    create(rep, title="دیروز", due_date=iso(today() - timedelta(days=1)))

    load = rep.get("/activities/workload").json()
    assert load["open_count"] == 4
    assert load["overdue_count"] == 1
    assert load["timed_minutes"] == 105
    assert load["overlaps"] == [{"first": a["id"], "second": b["id"]}]


def test_day_schedule_visibility(org: Org) -> None:
    create(login_as(org.rep2.id), start_time="09:00")
    params = {"owner_id": str(org.rep2.id), "day": iso(today())}
    assert login_as(org.rep1.id).get("/activities/day", params=params).status_code == 403
    assert len(login_as(org.manager.id).get("/activities/day", params=params).json()) == 1


# -- notes & timeline (criterion 14) ---------------------------------------------


def test_deal_timeline_holds_only_that_deal(org: Org) -> None:
    rep = login_as(org.rep1.id)
    customer = make_customer(rep)
    deal = make_deal(rep, customer)
    other = make_deal(rep, customer, title="فروش دیگر")
    activity = create(rep, deal_id=deal["id"])
    rep.post(
        f"/activities/{activity['id']}/complete", json={"outcome": "پیشنهاد ارسال شد", "version": 1}
    )
    rep.post("/notes", json={"body": "یادداشت این فروش", "deal_id": deal["id"]})
    rep.post("/notes", json={"body": "یادداشت فروش دیگر", "deal_id": other["id"]})

    items = rep.get("/timeline", params={"deal_id": deal["id"]}).json()["items"]
    kinds = [i["kind"] for i in items]
    assert kinds.count("activity") == 1 and kinds.count("note") == 1 and "stage" in kinds
    assert all(i["body"] != "یادداشت فروش دیگر" for i in items)
    notes_only = rep.get("/timeline", params={"deal_id": deal["id"], "kinds": ["note"]}).json()[
        "items"
    ]
    assert [i["body"] for i in notes_only] == ["یادداشت این فروش"]


def test_customer_timeline_hides_other_owners_deals(org: Org) -> None:
    rep1, rep2, manager = login_as(org.rep1.id), login_as(org.rep2.id), login_as(org.manager.id)
    customer = make_customer(rep1)
    # The manager opens a deal on rep1's customer and gives it to rep2.
    foreign = make_deal(manager, customer, owner_id=str(org.rep2.id), title="فروش همکار")
    rep2.post("/notes", json={"body": "یادداشت محرمانه همکار", "deal_id": foreign["id"]})
    rep1.post("/notes", json={"body": "یادداشت مشتری", "customer_id": customer})

    bodies = [
        i["body"] for i in rep1.get("/timeline", params={"customer_id": customer}).json()["items"]
    ]
    assert "یادداشت مشتری" in bodies and "یادداشت محرمانه همکار" not in bodies
    manager_bodies = [
        i["body"]
        for i in manager.get("/timeline", params={"customer_id": customer}).json()["items"]
    ]
    assert "یادداشت محرمانه همکار" in manager_bodies
    assert rep1.get("/timeline", params={"deal_id": foreign["id"]}).status_code == 403


def test_timeline_pages_with_cursor(org: Org) -> None:
    rep = login_as(org.rep1.id)
    customer = make_customer(rep)
    for i in range(5):
        rep.post("/notes", json={"body": f"یادداشت {i}", "customer_id": customer})
    first = rep.get("/timeline", params={"customer_id": customer, "limit": 3}).json()
    assert len(first["items"]) == 3 and first["has_more"] is True
    second = rep.get(
        "/timeline",
        params={"customer_id": customer, "limit": 3, "before": first["items"][-1]["at"]},
    ).json()
    assert len(second["items"]) == 2 and second["has_more"] is False
