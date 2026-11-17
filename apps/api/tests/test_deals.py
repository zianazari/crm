"""Deals, board, closing, reopening and payments.

Covers acceptance criteria 5, 7 and 19 and the section 0 decisions on the pipeline
(one final-result column) and on "won = contract" with an unpaid balance.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.modules.sales.models import DealHistory, Stage
from tests.conftest import Org, login_as


def stage_ids() -> list[str]:
    with SessionLocal() as db:
        return [
            str(s)
            for s in db.scalars(
                select(Stage.id).where(Stage.is_active.is_(True)).order_by(Stage.sort_order)
            )
        ]


def make_customer(client: TestClient, name: str = "شرکت آبان", mobile: str = "09121111111") -> str:
    r = client.post(
        "/customers", json={"full_name": name, "mobile": mobile, "allow_duplicate": True}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def make_deal(client: TestClient, customer_id: str, **fields: Any) -> dict[str, Any]:
    body = {"title": "پیاده‌سازی CRM", "customer_id": customer_id, "amount": 450_000_000, **fields}
    r = client.post("/deals", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def win(client: TestClient, deal: dict[str, Any], amount: int = 600_000_000) -> dict[str, Any]:
    r = client.post(
        f"/deals/{deal['id']}/win",
        json={"contract_amount": amount, "contract_date": "2026-11-10", "version": deal["version"]},
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


# -- creating ------------------------------------------------------------------


def test_deal_starts_in_first_stage_with_history(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep))
    assert deal["stage"]["id"] == stage_ids()[0]
    assert deal["status"] == "open" and deal["version"] == 1
    history = rep.get(f"/deals/{deal['id']}/history").json()
    assert [h["to_status"] for h in history] == ["open"]


def test_rep_cannot_open_deal_on_someone_elses_customer(org: Org) -> None:
    other_customer = make_customer(login_as(org.rep2.id))
    r = login_as(org.rep1.id).post("/deals", json={"title": "فروش", "customer_id": other_customer})
    assert r.status_code == 403


def test_organization_must_belong_to_customer(org: Org) -> None:
    rep = login_as(org.rep1.id)
    organization = rep.post("/organizations", json={"name": "گروه سپهر"}).json()
    r = rep.post(
        "/deals",
        json={
            "title": "فروش",
            "customer_id": make_customer(rep),
            "organization_id": organization["id"],
        },
    )
    assert r.status_code == 422


def test_two_independent_deals_for_one_customer(org: Org) -> None:
    """Acceptance criterion 5: a repeat purchase keeps its own stage and history."""
    rep = login_as(org.rep1.id)
    customer = make_customer(rep)
    first = make_deal(rep, customer, title="لایسنس سالانه")
    second = make_deal(rep, customer, title="خدمات راه‌اندازی")
    rep.post(f"/deals/{second['id']}/move", json={"stage_id": stage_ids()[2], "version": 1})

    deals = {
        d["title"]: d for d in rep.get("/deals", params={"customer_id": customer}).json()["items"]
    }
    assert deals["لایسنس سالانه"]["stage"]["id"] == stage_ids()[0]
    assert deals["خدمات راه‌اندازی"]["stage"]["id"] == stage_ids()[2]
    assert first["id"] != second["id"]


# -- visibility ---------------------------------------------------------------


def test_others_deals_show_only_current_status(org: Org) -> None:
    rep2 = login_as(org.rep2.id)
    deal = make_deal(rep2, make_customer(rep2, "فروشگاه نارون", "09122222222"))
    seen = login_as(org.rep1.id).get(f"/deals/{deal['id']}").json()
    assert seen["access"] == "limited"
    assert seen["customer"]["full_name"] == "فروشگاه نارون"
    assert seen["stage"]["name"] == "بررسی نیاز" and seen["status"] == "open"
    assert "amount" not in seen and "description" not in seen
    assert login_as(org.rep1.id).get(f"/deals/{deal['id']}/payments").status_code == 403


def test_board_totals_match_visible_cards(org: Org) -> None:
    """Acceptance criterion 19, with others' amounts hidden from a rep."""
    rep1, rep2 = login_as(org.rep1.id), login_as(org.rep2.id)
    make_deal(rep1, make_customer(rep1), amount=100)
    make_deal(rep1, make_customer(rep1, "گروه سپهر", "09123333333"), amount=250)
    make_deal(rep2, make_customer(rep2, "شرکت آریا", "09124444444"), amount=9_999)

    board = rep1.get("/deals/board").json()
    assert [c["stage"]["name"] for c in board["columns"]] == [
        "بررسی نیاز",
        "گفت‌وگو",
        "پیشنهاد قیمت",
        "توافق نهایی",
    ]
    first = board["columns"][0]
    assert first["count"] == 3
    assert first["total_amount"] == 350
    visible = sum(d.get("amount") or 0 for d in first["deals"])
    assert visible == first["total_amount"]

    manager_board = login_as(org.manager.id).get("/deals/board").json()
    assert manager_board["columns"][0]["total_amount"] == 10_349


def test_board_filters_apply_to_totals(org: Org) -> None:
    rep1, rep2 = login_as(org.rep1.id), login_as(org.rep2.id)
    make_deal(rep1, make_customer(rep1), amount=100)
    make_deal(rep2, make_customer(rep2, "شرکت آریا", "09124444444"), amount=200)
    manager = login_as(org.manager.id)
    column = manager.get("/deals/board", params={"owner_id": str(org.rep2.id)}).json()["columns"][0]
    assert (column["count"], column["total_amount"]) == (1, 200)


# -- moving and conflicts -----------------------------------------------------


def test_move_records_history_and_rejects_stale_version(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep))
    stages = stage_ids()

    moved = rep.post(f"/deals/{deal['id']}/move", json={"stage_id": stages[1], "version": 1})
    assert moved.status_code == 200 and moved.json()["version"] == 2

    # A second user still holding version 1 is told, and gets the current state back.
    stale = rep.post(f"/deals/{deal['id']}/move", json={"stage_id": stages[3], "version": 1})
    assert stale.status_code == 409
    assert stale.json()["current"]["stage"]["id"] == stages[1]

    with SessionLocal() as db:
        moves = db.scalars(select(DealHistory).where(DealHistory.from_stage_id.is_not(None))).all()
        assert [(str(m.from_stage_id), str(m.to_stage_id)) for m in moves] == [
            (stages[0], stages[1])
        ]


def test_other_rep_cannot_move_deal(org: Org) -> None:
    rep2 = login_as(org.rep2.id)
    deal = make_deal(rep2, make_customer(rep2))
    r = login_as(org.rep1.id).post(
        f"/deals/{deal['id']}/move", json={"stage_id": stage_ids()[1], "version": 1}
    )
    assert r.status_code == 403


# -- closing ------------------------------------------------------------------


def test_win_requires_contract_and_lands_in_outcome_column(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep))
    assert rep.post(f"/deals/{deal['id']}/win", json={"version": 1}).status_code == 422

    won = win(rep, deal)
    assert won["status"] == "won" and won["contract_amount"] == 600_000_000
    assert won["outstanding_amount"] == 600_000_000

    board = rep.get("/deals/board").json()
    assert board["columns"][0]["count"] == 0
    assert board["outcome"]["won_count"] == 1
    assert board["outcome"]["won_total"] == 600_000_000
    # Closed deals cannot be dragged between stages.
    r = rep.post(f"/deals/{deal['id']}/move", json={"stage_id": stage_ids()[1], "version": 2})
    assert r.status_code == 409


def test_lose_requires_reason(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep))
    assert rep.post(f"/deals/{deal['id']}/lose", json={"version": 1}).status_code == 422
    lost = rep.post(
        f"/deals/{deal['id']}/lose", json={"lost_reason": "قیمت بالا", "version": 1}
    ).json()
    assert lost["status"] == "lost" and lost["lost_reason"] == "قیمت بالا"
    assert rep.get("/deals/board").json()["outcome"]["lost_count"] == 1


def test_only_managers_reopen_and_history_keeps_contract(org: Org) -> None:
    rep = login_as(org.rep1.id)
    won = win(rep, make_deal(rep, make_customer(rep)))
    body = {"reason": "قرارداد لغو شد", "version": won["version"]}
    assert rep.post(f"/deals/{won['id']}/reopen", json=body).status_code == 403

    reopened = login_as(org.manager.id).post(f"/deals/{won['id']}/reopen", json=body).json()
    assert reopened["status"] == "open" and reopened["contract_amount"] is None
    latest = rep.get(f"/deals/{won['id']}/history").json()[0]
    assert latest["from_status"] == "won" and latest["to_status"] == "open"
    assert latest["reason"] == "قرارداد لغو شد"
    with SessionLocal() as db:
        entry = db.scalars(select(DealHistory).where(DealHistory.reason == "قرارداد لغو شد")).one()
        assert entry.details is not None and entry.details["contract_amount"] == 600_000_000


# -- payments (criterion 7) ---------------------------------------------------


def test_payments_refunds_and_unpaid_balance(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = win(rep, make_deal(rep, make_customer(rep)), amount=1_000)

    for amount in (300, 200):
        r = rep.post(
            f"/deals/{deal['id']}/payments", json={"amount": amount, "paid_on": "2026-11-12"}
        )
        assert r.status_code == 201
    refund = rep.post(
        f"/deals/{deal['id']}/payments",
        json={"kind": "refund", "amount": 100, "paid_on": "2026-11-13"},
    )
    assert refund.status_code == 201

    current = rep.get(f"/deals/{deal['id']}").json()
    assert current["paid_amount"] == 400
    assert current["outstanding_amount"] == 600

    too_much = rep.post(
        f"/deals/{deal['id']}/payments",
        json={"kind": "refund", "amount": 401, "paid_on": "2026-11-13"},
    )
    assert too_much.status_code == 422


def test_payments_are_voided_not_deleted_and_only_by_managers(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = win(rep, make_deal(rep, make_customer(rep)), amount=1_000)
    payment = rep.post(
        f"/deals/{deal['id']}/payments", json={"amount": 300, "paid_on": "2026-11-12"}
    ).json()
    path = f"/deals/{deal['id']}/payments/{payment['id']}/void"

    assert rep.post(path, json={"reason": "اشتباه"}).status_code == 403
    voided = login_as(org.manager.id).post(path, json={"reason": "ثبت تکراری"})
    assert voided.status_code == 200 and voided.json()["void_reason"] == "ثبت تکراری"

    assert rep.get(f"/deals/{deal['id']}").json()["paid_amount"] == 0
    # Still listed, marked as voided.
    assert len(rep.get(f"/deals/{deal['id']}/payments").json()) == 1


def test_no_payments_on_lost_deal(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep))
    rep.post(f"/deals/{deal['id']}/lose", json={"lost_reason": "انصراف", "version": 1})
    r = rep.post(f"/deals/{deal['id']}/payments", json={"amount": 10, "paid_on": "2026-11-12"})
    assert r.status_code == 409


# -- related rules -------------------------------------------------------------


def test_customer_with_open_deal_cannot_be_archived(org: Org) -> None:
    rep = login_as(org.rep1.id)
    customer = make_customer(rep)
    deal = make_deal(rep, customer)
    manager = login_as(org.manager.id)
    assert manager.post(f"/customers/{customer}/archive").status_code == 409
    rep.post(f"/deals/{deal['id']}/lose", json={"lost_reason": "انصراف", "version": 1})
    assert manager.post(f"/customers/{customer}/archive").status_code == 200


def test_retiring_a_stage_moves_its_open_deals(org: Org) -> None:
    manager = login_as(org.manager.id)
    extra = manager.post("/stages", json={"name": "دمو", "sort_order": 1}).json()
    deal = make_deal(manager, make_customer(manager), stage_id=extra["id"])

    assert (
        login_as(org.rep1.id).post(f"/stages/{extra['id']}/deactivate", json={}).status_code == 403
    )
    assert manager.post(f"/stages/{extra['id']}/deactivate", json={}).status_code == 409
    target = stage_ids()[0]
    r = manager.post(f"/stages/{extra['id']}/deactivate", json={"move_to_stage_id": target})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert manager.get(f"/deals/{deal['id']}").json()["stage"]["id"] == target


@pytest.fixture(autouse=True)
def _drop_extra_stages() -> Any:
    yield
    with SessionLocal() as db:
        db.execute(text("TRUNCATE deals CASCADE"))
        seeded = {"بررسی نیاز", "گفت‌وگو", "پیشنهاد قیمت", "توافق نهایی"}
        for stage in db.scalars(select(Stage)):
            if stage.name not in seeded:
                db.delete(stage)
        db.commit()
