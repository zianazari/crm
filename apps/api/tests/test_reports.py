"""Overview and report figures (spec 4.4; criteria 7, 19, 22) and their access scope."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.db.session import SessionLocal
from app.modules.activities.service import today
from app.modules.sales.models import Deal
from tests.conftest import Org, login_as
from tests.test_deals import make_customer, make_deal

PERIOD = {"date_from": (today() - timedelta(days=3)).isoformat(), "date_to": today().isoformat()}


def win(client: TestClient, deal: dict[str, Any], amount: int, on: date | None = None) -> None:
    r = client.post(
        f"/deals/{deal['id']}/win",
        json={
            "contract_amount": amount,
            "contract_date": (on or today()).isoformat(),
            "version": deal["version"],
        },
    )
    assert r.status_code == 200, r.text


def summary(client: TestClient, **params: Any) -> dict[str, Any]:
    r = client.get("/reports/summary", params={**PERIOD, **params})
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_sales_received_unpaid_and_pipeline_are_separate(org: Org) -> None:
    rep1, rep2 = login_as(org.rep1.id), login_as(org.rep2.id)
    customer = make_customer(rep1)
    won = make_deal(rep1, customer, title="فروش الف")
    win(rep1, won, 1_000)
    rep1.post(f"/deals/{won['id']}/payments", json={"amount": 300, "paid_on": today().isoformat()})
    rep1.post(
        f"/deals/{won['id']}/payments",
        json={"kind": "refund", "amount": 100, "paid_on": today().isoformat()},
    )
    make_deal(rep1, customer, title="باز", amount=200)
    win(rep2, make_deal(rep2, make_customer(rep2, "دیگری", "09122222222")), 5_000)

    mine = summary(rep1)
    assert mine["currency"] == "IRT"
    assert mine["sales"] == {"count": 1, "amount": 1_000}
    assert mine["received"] == 200
    assert mine["unpaid_balance"] == 800
    assert mine["pipeline"] == {"count": 1, "amount": 200}
    assert mine["deals_without_next_action"] == 1

    team = summary(login_as(org.manager.id))
    assert team["sales"] == {"count": 2, "amount": 6_000}


def test_contract_date_decides_the_sales_period(org: Org) -> None:
    rep = login_as(org.rep1.id)
    old = make_deal(rep, make_customer(rep))
    win(rep, old, 700, on=today() - timedelta(days=400))
    result = summary(rep)
    assert result["sales"]["count"] == 0
    # Still owed, whenever it was signed.
    assert result["unpaid_balance"] == 700


def test_win_rate_counts_only_deals_closed_in_period(org: Org) -> None:
    rep = login_as(org.rep1.id)
    assert summary(rep)["win_rate"]["rate"] is None  # nothing closed: "—", not 0 %
    customer = make_customer(rep)
    win(rep, make_deal(rep, customer, title="فروش الف"), 100)
    lost = make_deal(rep, customer, title="فروش ب")
    rep.post(f"/deals/{lost['id']}/lose", json={"lost_reason": "قیمت", "version": 1})
    assert summary(rep)["win_rate"] == {"numerator": 1, "denominator": 2, "rate": 0.5}


def test_lead_conversion_and_first_purchase(org: Org) -> None:
    rep = login_as(org.rep1.id)
    buyer = rep.post("/leads", json={"full_name": "خریدار", "mobile": "09123333333"}).json()
    rep.post("/leads", json={"full_name": "بی‌خرید", "mobile": "09124444444"})
    converted = rep.post(f"/leads/{buyer['id']}/convert", json={}).json()
    win(rep, make_deal(rep, converted["customer_id"]), 500)

    # A returning customer whose first purchase was long ago is not "first purchase".
    returning = make_customer(rep, "قدیمی", "09125555555")
    win(rep, make_deal(rep, returning, title="قبلی"), 100, on=today() - timedelta(days=300))
    win(rep, make_deal(rep, returning, title="جدید"), 100)

    result = summary(rep)
    assert result["new_leads"] == 2
    assert result["lead_conversion"] == {"numerator": 1, "denominator": 2, "rate": 0.5}
    assert result["first_purchase_customers"] == 1


def test_scope_and_filters(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    assert (
        rep1.get("/reports/summary", params={**PERIOD, "owner_id": str(org.rep2.id)}).status_code
        == 403
    )
    manager = login_as(org.manager.id)
    r = manager.get("/reports/summary", params={**PERIOD, "owner_id": str(org.other_rep.id)})
    assert r.status_code == 403
    bad = {"date_from": PERIOD["date_to"], "date_to": PERIOD["date_from"]}
    assert rep1.get("/reports/summary", params=bad).status_code == 422


def test_inbound_by_creator_survives_reassignment_and_uses_contract_amount(org: Org) -> None:
    rep1, manager = login_as(org.rep1.id), login_as(org.manager.id)
    deal = make_deal(rep1, make_customer(rep1), amount=300)
    manager.post(f"/deals/{deal['id']}/assign", json={"owner_id": str(org.rep2.id)})
    other = make_deal(rep1, make_customer(rep1, "شرکت ب", "09126666666"), amount=50)
    win(rep1, other, 900)

    rows = manager.get(
        "/reports/inbound-deals", params={**PERIOD, "group": "user", "measure": "amount"}
    ).json()["rows"]
    assert [(r["label"], r["open"], r["won"]) for r in rows] == [("کارشناس ۱", 300, 900)]
    by_time = manager.get("/reports/inbound-deals", params={**PERIOD, "group": "time"}).json()[
        "rows"
    ]
    assert sum(r["open"] + r["won"] + r["lost"] for r in by_time) == 2


def test_series_and_breakdowns(org: Org) -> None:
    rep = login_as(org.rep1.id)
    customer = make_customer(rep)
    win(rep, make_deal(rep, customer, title="فروش الف"), 100)
    win(rep, make_deal(rep, customer, title="فروش ب"), 250)
    lost = make_deal(rep, customer, title="فروش ج")
    rep.post(f"/deals/{lost['id']}/lose", json={"lost_reason": "قیمت بالا", "version": 1})

    points = rep.get("/reports/series", params={**PERIOD, "metric": "sales_amount"}).json()
    assert points == [{"date": today().isoformat(), "value": 350}]
    assert rep.get("/reports/lost-reasons", params=PERIOD).json() == [
        {"reason": "قیمت بالا", "count": 1}
    ]
    sources = rep.get("/reports/sales-by-source", params=PERIOD).json()
    assert sources == [{"source": "نامشخص", "won_count": 2, "won_amount": 350}]


def test_pipeline_and_needs_follow_up(org: Org) -> None:
    rep = login_as(org.rep1.id)
    customer = make_customer(rep)
    bare = make_deal(rep, customer, title="بدون پیگیری", amount=10)
    late = make_deal(rep, customer, title="معوق", amount=20)
    planned = make_deal(rep, customer, title="برنامه‌دار", amount=30)
    yesterday = (today() - timedelta(days=1)).isoformat()
    rep.post(
        "/activities",
        json={"type": "call", "title": "تماس", "due_date": yesterday, "deal_id": late["id"]},
    )
    rep.post(
        "/activities",
        json={
            "type": "call",
            "title": "تماس",
            "due_date": today().isoformat(),
            "deal_id": planned["id"],
        },
    )

    first_stage = rep.get("/reports/pipeline").json()[0]
    assert (first_stage["count"], first_stage["amount"]) == (3, 60)
    rows = {r["title"]: r["reason"] for r in rep.get("/reports/needs-follow-up").json()}
    assert rows == {"بدون پیگیری": "no_next_action", "معوق": "overdue"}
    assert bare["id"]


def test_team_performance_lists_team_with_attribution(org: Org) -> None:
    rep1, rep2 = login_as(org.rep1.id), login_as(org.rep2.id)
    win(rep1, make_deal(rep1, make_customer(rep1)), 400)
    lost = make_deal(rep2, make_customer(rep2, "ب ب", "09127777777"))
    rep2.post(f"/deals/{lost['id']}/lose", json={"lost_reason": "انصراف", "version": 1})

    rows = {
        r["user"]["full_name"]: r
        for r in login_as(org.manager.id).get("/reports/team", params=PERIOD).json()
    }
    assert set(rows) == {"مدیر الف", "کارشناس ۱", "کارشناس ۲"}
    assert (rows["کارشناس ۱"]["won_amount"], rows["کارشناس ۱"]["win_rate"]) == (400, 1.0)
    assert (rows["کارشناس ۲"]["lost_count"], rows["کارشناس ۲"]["win_rate"]) == (1, 0.0)
    assert rows["مدیر الف"]["win_rate"] is None
    only_me = login_as(org.rep1.id).get("/reports/team", params=PERIOD).json()
    assert [r["user"]["full_name"] for r in only_me] == ["کارشناس ۱"]


def test_archived_deals_are_left_out(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep))
    win(rep, deal, 999)
    with SessionLocal() as db:
        db.execute(update(Deal).values(archived_at=Deal.created_at))
        db.commit()
    assert summary(rep)["sales"]["count"] == 0
