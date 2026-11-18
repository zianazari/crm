"""User, team and audit administration (spec 5 and 10)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.main import app
from app.modules.auth.deps import get_otp_sender
from app.modules.crm.models import OwnershipHistory
from app.modules.identity.models import Team
from tests.conftest import Org, login_as
from tests.test_auth import CapturingSender
from tests.test_deals import make_customer, make_deal


def actions(admin: TestClient) -> list[str]:
    return [row["action"] for row in admin.get("/audit").json()["items"]]


# -- users -------------------------------------------------------------------


def test_admin_creates_user_with_normalized_unique_contacts(org: Org) -> None:
    admin = login_as(org.admin.id)
    r = admin.post(
        "/users",
        json={
            "full_name": "نیما کاظمی",
            "mobile": "۰۹۱۲ ۹۹۹ ۸۸۷۷",
            "role": "sales_rep",
            "team_id": None,
        },
    )
    assert r.status_code == 201 and r.json()["mobile"] == "+989129998877"
    dup = admin.post("/users", json={"full_name": "تکراری", "mobile": "09129998877"})
    assert dup.status_code == 409
    assert admin.post("/users", json={"full_name": "بدون تماس"}).status_code == 422
    assert "user.created" in actions(admin)


def test_only_admin_manages_users_and_managers_see_their_team(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    assert (
        manager.post("/users", json={"full_name": "کسی", "mobile": "09120001111"}).status_code
        == 403
    )
    assert rep.get("/users").status_code == 403
    names = {u["full_name"] for u in manager.get("/users").json()}
    assert names == {"مدیر الف", "کارشناس ۱", "کارشناس ۲"}


def test_role_change_is_audited_and_demotion_frees_the_team(org: Org) -> None:
    admin = login_as(org.admin.id)
    r = admin.patch(f"/users/{org.manager.id}", json={"role": "sales_rep"})
    assert r.status_code == 200 and r.json()["manages_team"] is None
    with SessionLocal() as db:
        team = db.scalars(select(Team).where(Team.name == "فروش الف")).one()
        assert team.manager_id is None
    entry = admin.get("/audit", params={"action": "user.updated"}).json()["items"][0]
    assert entry["details"]["role"] == {"from": "sales_manager", "to": "sales_rep"}
    assert admin.patch(f"/users/{org.admin.id}", json={"role": "sales_rep"}).status_code == 422


def test_deactivation_requires_a_decision_on_open_work(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    make_deal(rep1, make_customer(rep1))
    admin = login_as(org.admin.id)
    items = admin.get(f"/users/{org.rep1.id}/open-items").json()
    assert items == {"leads": 0, "customers": 1, "deals": 1, "activities": 0}
    assert admin.post(f"/users/{org.rep1.id}/deactivate", json={}).status_code == 409
    assert (
        admin.post(f"/users/{org.admin.id}/deactivate", json={"leave_open_items": True}).status_code
        == 422
    )


def test_deactivation_transfers_work_and_ends_sessions(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    customer = make_customer(rep1)
    deal = make_deal(rep1, customer)
    rep1.post(
        "/activities",
        json={"type": "call", "title": "تماس", "due_date": "2030-01-01", "deal_id": deal["id"]},
    )
    lead = rep1.post("/leads", json={"full_name": "سرنخ باز", "mobile": "09123334444"}).json()

    admin = login_as(org.admin.id)
    r = admin.post(f"/users/{org.rep1.id}/deactivate", json={"transfer_to_id": str(org.rep2.id)})
    assert r.status_code == 200 and r.json()["is_active"] is False

    # Sessions end immediately (spec 5).
    assert rep1.get("/auth/me").status_code == 401
    rep2 = login_as(org.rep2.id)
    assert rep2.get(f"/deals/{deal['id']}").json()["access"] == "full"
    assert rep2.get(f"/customers/{customer}").json()["access"] == "full"
    assert rep2.get(f"/leads/{lead['id']}").json()["access"] == "full"
    assert rep2.get("/activities", params={"mine": True}).json()["total"] == 1
    with SessionLocal() as db:
        moved = db.scalars(select(OwnershipHistory.entity_type)).all()
        assert sorted(moved) == ["customer", "deal", "lead"]

    assert admin.post(f"/users/{org.rep1.id}/reactivate").status_code == 200
    assert {"user.deactivated", "user.reactivated"} <= set(actions(admin))


# -- teams -------------------------------------------------------------------


def test_team_manager_rules(org: Org) -> None:
    admin = login_as(org.admin.id)
    # A manager runs exactly one team.
    r = admin.post("/teams", json={"name": "تیم سوم", "manager_id": str(org.manager.id)})
    assert r.status_code == 409
    # Only sales managers can lead a team.
    r = admin.post("/teams", json={"name": "تیم سوم", "manager_id": str(org.rep1.id)})
    assert r.status_code == 422
    created = admin.post("/teams", json={"name": "تیم سوم"})
    assert created.status_code == 201
    assert admin.post("/teams", json={"name": "تیم سوم"}).status_code == 409

    mine = login_as(org.manager.id).get("/teams").json()
    assert [t["name"] for t in mine] == ["فروش الف"] and mine[0]["member_count"] == 3
    assert login_as(org.rep1.id).get("/teams").status_code == 403


def test_inactive_team_gives_manager_no_team_scope(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    deal = make_deal(rep1, make_customer(rep1))
    admin = login_as(org.admin.id)
    team = next(t for t in admin.get("/teams").json() if t["name"] == "فروش الف")
    admin.patch(
        f"/teams/{team['id']}",
        json={"name": "فروش الف", "manager_id": str(org.manager.id), "is_active": False},
    )
    assert login_as(org.manager.id).get(f"/deals/{deal['id']}").json()["access"] == "limited"


# -- audit -------------------------------------------------------------------


@pytest.fixture
def sender() -> Any:
    capturing = CapturingSender()
    app.dependency_overrides[get_otp_sender] = lambda: capturing
    yield capturing
    app.dependency_overrides.clear()


def test_login_logout_and_settings_are_audited(org: Org, sender: CapturingSender) -> None:
    client = TestClient(app)
    challenge = client.post(
        "/auth/otp/request", json={"channel": "sms", "destination": "09100000003"}
    ).json()
    client.post(
        "/auth/otp/verify",
        json={"challenge_id": challenge["challenge_id"], "code": sender.last_code},
    )
    client.post("/auth/logout", headers={"X-CSRF-Token": client.cookies.get("crm_csrf") or ""})
    manager = login_as(org.manager.id)
    manager.post("/stages", json={"name": "دمو", "sort_order": 9})

    admin = login_as(org.admin.id)
    logged = actions(admin)
    assert {"auth.login", "auth.logout", "stage.created"} <= set(logged)
    assert login_as(org.manager.id).get("/audit").status_code == 403


@pytest.fixture(autouse=True)
def _drop_extra_stages() -> Any:
    yield
    with SessionLocal() as db:
        db.execute(text("TRUNCATE deals CASCADE"))
        db.execute(
            text("DELETE FROM pipeline_stages WHERE name NOT IN (:a, :b, :c, :d)"),
            {"a": "بررسی نیاز", "b": "گفت‌وگو", "c": "پیشنهاد قیمت", "d": "توافق نهایی"},
        )
        db.commit()
