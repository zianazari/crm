"""One-off template messages from a record (spec section 5: «ارسال تکی قالب مجاز در
پرونده خود با کنترل مصرف»)."""

import uuid
from collections.abc import Iterator
from datetime import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.modules.campaigns import audience as aud
from app.modules.campaigns import service
from app.modules.campaigns.models import Suppression
from app.modules.identity.models import Role, Team, TeamKind, User
from app.modules.messaging.models import Channel, OutboundMessage, OutboxEvent, Purpose
from tests.conftest import Org, login_as
from tests.test_deals import make_deal


@pytest.fixture(autouse=True)
def _clean_messages() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        db.execute(delete(OutboxEvent))
        db.execute(delete(OutboundMessage))
        db.commit()


@pytest.fixture(autouse=True)
def _open_all_day() -> None:
    set_policy(window_start=time(0, 0), window_end=time(23, 59, 59))


def set_policy(**values: Any) -> None:
    with SessionLocal() as db:
        rules = service.policy(db)
        for key, value in values.items():
            setattr(rules, key, value)
        db.commit()


def template(client: TestClient, kind: str = "service", **fields: Any) -> dict[str, Any]:
    body = {
        "name": "یادآوری فاکتور" if kind == "service" else "پیشنهاد ویژه",
        "channel": "sms",
        "kind": kind,
        "body": "{name} عزیز، {owner} از CRM هستم. فاکتور شما آماده است.",
        **fields,
    }
    r = client.post("/message-templates", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def customer(client: TestClient, mobile: str | None = "09121112233", consent: bool = False) -> str:
    r = client.post(
        "/customers",
        json={
            "full_name": "شرکت آبان",
            "mobile": mobile,
            "email": None if mobile else "aban@example.com",
            "sms_consent": consent,
            "allow_duplicate": True,
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def send(client: TestClient, template_id: str, **target: str) -> Any:
    return client.post(
        "/direct-messages",
        json={"template_id": template_id, "request_id": str(uuid.uuid4()), **target},
    )


def messages() -> list[OutboundMessage]:
    with SessionLocal() as db:
        return list(db.scalars(select(OutboundMessage).order_by(OutboundMessage.created_at)))


def test_templates_are_written_by_managers(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    t = template(manager)
    assert rep.post("/message-templates", json={**t, "name": "x y"}).status_code == 403
    off = template(manager, name="قدیمی", is_active=False)
    assert [x["id"] for x in rep.get("/message-templates").json()] == [t["id"]]
    listed = manager.get("/message-templates", params={"include_inactive": True}).json()
    assert {x["id"] for x in listed} == {t["id"], off["id"]}
    email = {"name": "ایمیل", "channel": "email", "kind": "service", "body": "سلام"}
    assert manager.post("/message-templates", json=email).status_code == 422  # needs subject


def test_rep_sends_a_service_template_from_own_record(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    t = template(manager)
    customer_id = customer(rep)
    check = rep.post(
        "/direct-messages/check", json={"template_id": t["id"], "customer_id": customer_id}
    ).json()
    assert check["allowed"] and check["to"] == "+989121112233"
    assert check["text"] == "شرکت آبان عزیز، کارشناس ۱ از CRM هستم. فاکتور شما آماده است."
    assert check["sent_today"] == 0 and check["daily_limit"] == 20
    r = send(rep, t["id"], customer_id=customer_id)
    assert r.status_code == 201 and r.json()["status"] == "queued"
    [message] = messages()
    assert message.purpose is Purpose.NOTIFICATION and "/u/" not in (message.body or "")
    timeline = rep.get("/timeline", params={"customer_id": customer_id}).json()["items"]
    assert timeline[0]["kind"] == "message"
    assert timeline[0]["title"] == "پیامک «یادآوری فاکتور» به شرکت آبان"
    assert timeline[0]["message_status"] == "queued"


def test_only_from_records_one_sees_in_full(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    t = template(manager)
    others = customer(login_as(org.rep2.id))
    assert send(rep, t["id"], customer_id=others).status_code == 403
    assert send(manager, t["id"], customer_id=others).status_code == 201  # team manager
    with SessionLocal() as db:
        team = Team(name="مالی", kind=TeamKind.FINANCE)
        db.add(team)
        db.flush()
        finance = User(full_name="مالی", mobile="+989100000099", role=Role.SALES_REP, team=team)
        db.add(finance)
        db.commit()
        finance_id = finance.id
    assert login_as(finance_id).get("/message-templates").status_code == 403


def test_deal_messages_go_to_its_customer_and_show_on_both_timelines(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    t = template(manager, body="درباره {deal}: {name} عزیز، پیش‌فاکتور ارسال شد.")
    customer_id = customer(rep)
    deal = make_deal(rep, customer_id)
    r = send(rep, t["id"], deal_id=deal["id"])
    assert r.status_code == 201
    assert r.json()["text"] == "درباره پیاده‌سازی CRM: شرکت آبان عزیز، پیش‌فاکتور ارسال شد."
    on_deal = rep.get("/timeline", params={"deal_id": deal["id"]}).json()["items"]
    on_customer = rep.get("/timeline", params={"customer_id": customer_id}).json()["items"]
    assert [e["kind"] for e in on_deal if e["kind"] == "message"] == ["message"]
    [entry] = [e for e in on_customer if e["kind"] == "message"]
    assert entry["deal"]["id"] == deal["id"]


def test_marketing_needs_consent_and_carries_unsubscribe(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    t = template(manager, "marketing", body="{name} عزیز، تخفیف ویژه برای شما.")
    without = customer(rep, "09121110001")
    r = send(rep, t["id"], customer_id=without)
    assert r.status_code == 422 and r.json()["detail"] == aud.NO_CONSENT
    allowed = customer(rep, "09121110002", consent=True)
    assert send(rep, t["id"], customer_id=allowed).status_code == 201
    [message] = messages()
    assert message.purpose is Purpose.MARKETING and message.body is not None
    token = message.body.rsplit("/u/", 1)[1]
    anonymous = TestClient(app)
    assert anonymous.post(f"/public/unsubscribe/{token}").json()["unsubscribed"] is True
    again = send(rep, t["id"], customer_id=allowed)
    assert again.status_code == 422 and again.json()["detail"] in {aud.NO_CONSENT, aud.SUPPRESSED}


def test_marketing_respects_list_and_window_service_does_not_need_them(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    promo = template(manager, "marketing")
    info = template(manager)
    customer_id = customer(rep, "09121110003", consent=True)
    with SessionLocal() as db:
        db.add(Suppression(channel=Channel.SMS, address="+989121110003", reason="manual"))
        db.commit()
    assert send(rep, promo["id"], customer_id=customer_id).json()["detail"] == aud.SUPPRESSED
    assert send(rep, info["id"], customer_id=customer_id).status_code == 201
    set_policy(window_start=time(0, 0), window_end=time(0, 1))
    other = customer(rep, "09121110004", consent=True)
    blocked = send(rep, promo["id"], customer_id=other)
    assert blocked.status_code == 422 and "خارج از ساعت مجاز" in blocked.json()["detail"]
    assert send(rep, info["id"], customer_id=other).status_code == 201


def test_daily_limit_per_person_and_budget(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    t = template(manager)
    customer_id = customer(rep)
    set_policy(user_daily_limit=2)
    assert send(rep, t["id"], customer_id=customer_id).status_code == 201
    assert send(rep, t["id"], customer_id=customer_id).status_code == 201
    third = send(rep, t["id"], customer_id=customer_id)
    assert third.status_code == 422 and "سقف روزانه ارسال تکی" in third.json()["detail"]
    assert rep.get("/direct-messages/usage").json() == {"sent_today": 2, "daily_limit": 2}
    # Someone else's allowance is their own.
    assert send(manager, t["id"], customer_id=customer_id).status_code == 201
    set_policy(user_daily_limit=100, sms_unit_price=1000, monthly_budget=1500)
    fits = send(manager, t["id"], customer_id=customer_id)  # one part: 1000 of 1500
    assert fits.status_code == 201
    capped = send(manager, t["id"], customer_id=customer_id)
    assert capped.status_code == 422 and "سقف مصرف" in capped.json()["detail"]


def test_repeated_request_sends_once(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    t = template(manager)
    customer_id = customer(rep)
    body = {"template_id": t["id"], "customer_id": customer_id, "request_id": str(uuid.uuid4())}
    first = rep.post("/direct-messages", json=body).json()
    second = rep.post("/direct-messages", json=body).json()
    assert first["id"] == second["id"] and len(messages()) == 1


def test_no_address(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    t = template(manager)
    customer_id = customer(rep, mobile=None)
    check = rep.post(
        "/direct-messages/check", json={"template_id": t["id"], "customer_id": customer_id}
    ).json()
    assert check["allowed"] is False and check["reason"] == aud.NO_ADDRESS
