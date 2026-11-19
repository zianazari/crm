"""Customer portal and tickets (spec 4.9, section 5; criterion 17)."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.modules.auth.deps import get_otp_sender
from app.modules.identity.models import Role, Team, TeamKind, User
from app.modules.messaging.models import OutboundMessage, OutboxEvent, Purpose
from app.modules.notifications.models import Notification
from tests.conftest import Org, login_as
from tests.test_auth import CapturingSender


@pytest.fixture
def sender() -> Iterator[CapturingSender]:
    capturing = CapturingSender()
    app.dependency_overrides[get_otp_sender] = lambda: capturing
    yield capturing
    app.dependency_overrides.pop(get_otp_sender, None)


@pytest.fixture(autouse=True)
def _clean_messages() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        db.execute(delete(OutboxEvent))
        db.execute(delete(OutboundMessage))
        db.commit()


def customer(client: TestClient, name: str = "مریم مرادی", mobile: str = "09127778899") -> str:
    r = client.post(
        "/customers", json={"full_name": name, "mobile": mobile, "allow_duplicate": True}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def enable(client: TestClient, customer_id: str, channel: str = "sms") -> Any:
    return client.post("/portal-access", json={"customer_id": customer_id, "channel": channel})


def portal_login(sender: CapturingSender, mobile: str = "09127778899") -> TestClient:
    client = TestClient(app)
    r = client.post("/portal/auth/otp/request", json={"channel": "sms", "destination": mobile})
    assert r.status_code == 202, r.text
    challenge = r.json()["challenge_id"]
    verified = client.post(
        "/portal/auth/otp/verify", json={"challenge_id": challenge, "code": sender.last_code}
    )
    assert verified.status_code == 200, verified.text
    client.headers["X-CSRF-Token"] = client.cookies["crm_portal_csrf"]
    return client


def open_ticket(portal: TestClient, subject: str = "مشکل در فاکتور") -> dict[str, Any]:
    r = portal.post(
        "/portal/tickets",
        json={"subject": subject, "body": "مبلغ فاکتور آخر با قرارداد هم‌خوانی ندارد."},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


# -- portal access ------------------------------------------------------------------------


def test_access_is_given_from_the_record_and_one_address_one_customer(org: Org) -> None:
    rep = login_as(org.rep1.id)
    first = customer(rep)
    r = enable(rep, first)
    assert r.status_code == 201 and r.json()["address"] == "+989127778899"
    assert enable(rep, first, "email").status_code == 422  # no email on file
    same_number = customer(rep, "مریم (تکراری)")
    assert enable(rep, same_number).status_code == 409
    assert enable(login_as(org.rep2.id), first).status_code == 403
    assert len(rep.get("/portal-access", params={"customer_id": first}).json()) == 1


def test_only_addresses_with_access_get_a_code(org: Org, sender: CapturingSender) -> None:
    rep = login_as(org.rep1.id)
    customer(rep)  # on file, but no portal access yet
    anonymous = TestClient(app)
    r = anonymous.post(
        "/portal/auth/otp/request", json={"channel": "sms", "destination": "09127778899"}
    )
    assert r.status_code == 202 and sender.sent == []  # same answer, nothing sent


def test_portal_and_staff_codes_do_not_cross(org: Org, sender: CapturingSender) -> None:
    rep = login_as(org.rep1.id)
    enable(rep, customer(rep, mobile="09100000003"))  # the same number as rep1's login
    client = TestClient(app)
    staff = client.post(
        "/auth/otp/request", json={"channel": "sms", "destination": "09100000003"}
    ).json()["challenge_id"]
    code = sender.last_code
    wrong = client.post("/portal/auth/otp/verify", json={"challenge_id": staff, "code": code})
    assert wrong.status_code == 400
    get_redis().flushdb()  # clear cooldowns
    portal = client.post(
        "/portal/auth/otp/request", json={"channel": "sms", "destination": "09100000003"}
    ).json()["challenge_id"]
    wrong = client.post("/auth/otp/verify", json={"challenge_id": portal, "code": sender.last_code})
    assert wrong.status_code == 400


def test_disabling_access_ends_sessions(org: Org, sender: CapturingSender) -> None:
    rep = login_as(org.rep1.id)
    customer_id = customer(rep)
    identity = enable(rep, customer_id).json()
    portal = portal_login(sender)
    assert portal.get("/portal/me").json()["customer_name"] == "مریم مرادی"
    rep.post(f"/portal-access/{identity['id']}/disable")
    assert portal.get("/portal/me").status_code == 401
    assert portal.get("/portal/tickets").status_code == 401


# -- tickets ----------------------------------------------------------------------------------


def test_customer_opens_and_follows_own_tickets_only(org: Org, sender: CapturingSender) -> None:
    """Criterion 17."""
    rep = login_as(org.rep1.id)
    enable(rep, customer(rep))
    enable(rep, customer(rep, "علی رضایی", "09121234567"))
    mine = portal_login(sender)
    ticket = open_ticket(mine)
    assert ticket["status"] == "new" and ticket["number"] > 1000
    assert [m["from_me"] for m in ticket["messages"]] == [True]
    get_redis().flushdb()
    other = portal_login(sender, "09121234567")
    assert other.get(f"/portal/tickets/{ticket['id']}").status_code == 404
    assert (
        other.post(f"/portal/tickets/{ticket['id']}/messages", json={"body": "سلام"}).status_code
        == 404
    )
    assert other.get("/portal/tickets").json()["items"] == []
    # Without the CSRF header nothing changes.
    del mine.headers["X-CSRF-Token"]
    assert (
        mine.post("/portal/tickets", json={"subject": "abc", "body": "x" * 20}).status_code == 403
    )
    # Staff never use the portal API, nor the reverse.
    assert rep.get("/portal/tickets").status_code == 401
    assert other.get("/tickets").status_code == 401


def test_staff_reply_internal_note_and_status(org: Org, sender: CapturingSender) -> None:
    rep, manager = login_as(org.rep1.id), login_as(org.manager.id)
    enable(rep, customer(rep))
    portal = portal_login(sender)
    ticket = open_ticket(portal)
    with SessionLocal() as db:
        told = db.scalars(select(Notification.user_id).where(Notification.kind == "ticket")).all()
    assert told == [org.rep1.id]  # the customer's owner handles it

    staff = rep.get(f"/tickets/{ticket['id']}").json()
    assert staff["assignee"]["id"] == str(org.rep1.id) and staff["opened_by_customer"]
    assert login_as(org.rep2.id).get(f"/tickets/{ticket['id']}").status_code == 404
    assert manager.get(f"/tickets/{ticket['id']}").status_code == 200

    rep.post(
        f"/tickets/{ticket['id']}/messages",
        json={"body": "به واحد مالی اطلاع دادم.", "internal": True},
    )
    answered = rep.post(
        f"/tickets/{ticket['id']}/messages", json={"body": "فاکتور اصلاح‌شده ارسال شد."}
    ).json()
    assert answered["status"] == "waiting_customer"
    assert [m["internal"] for m in answered["messages"]] == [False, True, False]
    seen = portal.get(f"/portal/tickets/{ticket['id']}").json()
    assert [m["body"] for m in seen["messages"]] == [
        "مبلغ فاکتور آخر با قرارداد هم‌خوانی ندارد.",
        "فاکتور اصلاح‌شده ارسال شد.",
    ]
    assert seen["status_label"] == "منتظر پاسخ شما"
    with SessionLocal() as db:
        [note] = db.scalars(
            select(OutboundMessage).where(OutboundMessage.purpose == Purpose.NOTIFICATION)
        ).all()
    assert note.recipient == "+989127778899"
    assert (
        note.body and "فاکتور" not in note.body and f"/portal/tickets/{ticket['id']}" in note.body
    )

    back = portal.post(
        f"/portal/tickets/{ticket['id']}/messages", json={"body": "دریافت شد، ممنون."}
    )
    assert back.json()["status"] == "in_progress"
    closed = rep.post(f"/tickets/{ticket['id']}/status", json={"status": "closed"}).json()
    assert closed["status"] == "closed" and closed["closed_at"]
    # A reply on a closed ticket reopens it.
    assert (
        portal.post(
            f"/portal/tickets/{ticket['id']}/messages", json={"body": "یک سؤال دیگر"}
        ).json()["status"]
        == "in_progress"
    )


def test_assigning_is_for_managers_within_scope(org: Org, sender: CapturingSender) -> None:
    rep, manager = login_as(org.rep1.id), login_as(org.manager.id)
    enable(rep, customer(rep))
    ticket = open_ticket(portal_login(sender))
    body = {"user_id": str(org.rep2.id)}
    assert rep.post(f"/tickets/{ticket['id']}/assign", json=body).status_code == 403
    outside = {"user_id": str(org.other_rep.id)}
    assert manager.post(f"/tickets/{ticket['id']}/assign", json=outside).status_code == 422
    moved = manager.post(f"/tickets/{ticket['id']}/assign", json=body).json()
    assert moved["assignee"]["id"] == str(org.rep2.id)
    assert login_as(org.rep2.id).get(f"/tickets/{ticket['id']}").status_code == 200
    mine = login_as(org.rep2.id).get("/tickets", params={"mine": True}).json()
    assert [t["id"] for t in mine["items"]] == [ticket["id"]]


def test_staff_open_on_behalf_and_search(org: Org) -> None:
    rep = login_as(org.rep1.id)
    customer_id = customer(rep)
    r = rep.post(
        "/tickets",
        json={"customer_id": customer_id, "subject": "درخواست تمدید", "body": "تماس تلفنی مشتری"},
    )
    assert r.status_code == 201 and r.json()["status"] == "in_progress"
    number = r.json()["number"]
    found = rep.get("/tickets", params={"q": str(number)}).json()["items"]
    assert [t["number"] for t in found] == [number]
    assert rep.get("/tickets", params={"q": "تمدید"}).json()["total"] == 1
    other = customer(login_as(org.rep2.id), "دیگری", "09120001111")
    blocked = rep.post("/tickets", json={"customer_id": other, "subject": "abc", "body": "def"})
    assert blocked.status_code == 403


def test_rate_limit_and_lengths(org: Org, sender: CapturingSender) -> None:
    rep = login_as(org.rep1.id)
    enable(rep, customer(rep))
    portal = portal_login(sender)
    short = portal.post("/portal/tickets", json={"subject": "ab", "body": "کوتاه"})
    assert short.status_code == 422
    for i in range(10):
        open_ticket(portal, f"درخواست {i}")
    r = portal.post("/portal/tickets", json={"subject": "یازدهم", "body": "متن درخواست یازدهم"})
    assert r.status_code == 429


def test_deactivated_users_tickets_move_and_finance_has_no_tickets(
    org: Org, sender: CapturingSender
) -> None:
    rep = login_as(org.rep1.id)
    enable(rep, customer(rep))
    ticket = open_ticket(portal_login(sender))
    admin = login_as(org.admin.id)
    r = admin.post(f"/users/{org.rep1.id}/deactivate", json={"transfer_to_id": str(org.rep2.id)})
    assert r.status_code == 200, r.text
    assert login_as(org.rep2.id).get(f"/tickets/{ticket['id']}").json()["assignee"]["id"] == str(
        org.rep2.id
    )
    with SessionLocal() as db:
        team = Team(name="مالی", kind=TeamKind.FINANCE)
        db.add(team)
        db.flush()
        finance = User(full_name="مالی", mobile="+989100000099", role=Role.SALES_REP, team=team)
        db.add(finance)
        db.commit()
        finance_id = finance.id
    assert login_as(finance_id).get("/tickets").status_code == 403
    assert uuid.UUID(ticket["id"])
