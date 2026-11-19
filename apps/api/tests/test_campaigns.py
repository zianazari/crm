"""SMS and email campaigns (spec 4.5; criterion 8 and the campaign part of 10 and 11).

The worker step (``service.tick``) is called directly; ``now`` is passed in to test the
sending window.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.modules.campaigns import audience as aud
from app.modules.campaigns import service
from app.modules.campaigns.models import MessagingPolicy, Suppression
from app.modules.crm.models import Customer, Lead
from app.modules.identity.models import Role, Team, TeamKind, User
from app.modules.messaging.models import (
    Channel,
    MessageStatus,
    OutboundMessage,
    OutboxEvent,
    Purpose,
)
from app.modules.messaging.providers import Accepted, Providers
from app.modules.messaging.service import process
from app.modules.notifications.models import Notification
from tests.conftest import Org, login_as

TEHRAN = ZoneInfo("Asia/Tehran")


@pytest.fixture(autouse=True)
def _clean_messages() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        db.execute(delete(OutboxEvent))
        db.execute(delete(OutboundMessage))
        db.commit()


@pytest.fixture(autouse=True)
def _open_all_day() -> None:
    """Most tests send at any hour; the window test narrows it."""
    set_policy(window_start=time(0, 0), window_end=time(23, 59, 59))


def set_policy(**values: Any) -> None:
    with SessionLocal() as db:
        rules = service.policy(db)
        for key, value in values.items():
            setattr(rules, key, value)
        db.commit()


def tick(now: datetime | None = None) -> None:
    with SessionLocal() as db:
        assert service.tick(db, now)


def contact(
    client: TestClient,
    kind: str,
    name: str,
    mobile: str | None,
    *,
    consent: bool = True,
    email: str | None = None,
) -> dict[str, Any]:
    body = {
        "full_name": name,
        "mobile": mobile,
        "email": email,
        "sms_consent": consent,
        "email_consent": consent,
        "allow_duplicate": True,
    }
    r = client.post(f"/{kind}s", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def campaign(client: TestClient, audience: dict[str, Any], **fields: Any) -> dict[str, Any]:
    body = {
        "name": "تخفیف پاییزه",
        "channel": "sms",
        "body": "{name} عزیز، تخفیف ویژه پاییز برای شماست.",
        "audience": audience,
        **fields,
    }
    r = client.post("/campaigns", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def everyone() -> dict[str, Any]:
    return {"kind": "segment", "filters": {}}


def recipients(client: TestClient, campaign_id: str, **params: Any) -> list[dict[str, Any]]:
    r = client.get(f"/campaigns/{campaign_id}/recipients", params=params)
    assert r.status_code == 200, r.text
    return list(r.json()["items"])


def marketing_messages() -> list[OutboundMessage]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(OutboundMessage)
                .where(OutboundMessage.purpose == Purpose.MARKETING)
                .order_by(OutboundMessage.created_at)
            )
        )


# -- audience and preview -----------------------------------------------------------------


def test_preview_counts_and_reasons(org: Org) -> None:
    """Criterion 8: the count before running, and who is left out and why."""
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    contact(rep, "customer", "مریم", "09121110001")
    contact(rep, "lead", "مریم (سرنخ)", "0912 111 0001")  # same number: duplicate
    contact(rep, "customer", "بدون اجازه", "09121110002", consent=False)
    contact(rep, "lead", "بدون موبایل", None, email="a@example.com")
    contact(rep, "customer", "منصرف", "09121110003")
    contact(login_as(org.other_rep.id), "customer", "تیم دیگر", "09121110004")
    with SessionLocal() as db:
        db.add(Suppression(channel=Channel.SMS, address="+989121110003", reason="manual"))
        db.commit()
    c = campaign(manager, everyone())
    preview = manager.post(f"/campaigns/{c['id']}/preview").json()
    assert preview["contacts"] == 5  # the other team's contact is outside the scope
    assert preview["eligible"] == 1
    assert preview["excluded"] == {
        aud.DUPLICATE: 1,
        aud.NO_CONSENT: 1,
        aud.NO_ADDRESS: 1,
        aud.SUPPRESSED: 1,
    }
    assert preview["sample_name"] == "مریم"
    assert preview["sample_text"].startswith("مریم عزیز، تخفیف ویژه")
    assert "\nلغو: http://localhost:3000/u/" in preview["sample_text"]
    assert preview["parts"] == 2  # Persian: 70 characters per single part


def test_segment_filters_and_selected_contacts(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    tag = rep.post("/tags", json={"name": "وفادار"}).json()
    a = contact(rep, "customer", "الف", "09121110011")
    b = contact(rep, "customer", "بهار", "09121110012")
    lead = contact(rep, "lead", "جواد", "09121110013")
    rep.patch(f"/customers/{a['id']}", json={"tag_ids": [tag["id"]]})
    tagged = campaign(manager, {"kind": "segment", "filters": {"tag_ids": [tag["id"]]}})
    assert manager.post(f"/campaigns/{tagged['id']}/preview").json()["sample_name"] == "الف"
    leads_only = campaign(manager, {"kind": "segment", "filters": {"contact_types": ["lead"]}})
    assert manager.post(f"/campaigns/{leads_only['id']}/preview").json()["eligible"] == 1
    chosen = campaign(
        manager,
        {
            "kind": "selected",
            "contacts": [{"type": "customer", "id": b["id"]}, {"type": "lead", "id": lead["id"]}],
        },
    )
    assert manager.post(f"/campaigns/{chosen['id']}/preview").json()["eligible"] == 2


def test_sms_parts() -> None:
    assert aud.sms_parts("a" * 160) == 1 and aud.sms_parts("a" * 161) == 2
    assert aud.sms_parts("س" * 70) == 1 and aud.sms_parts("س" * 71) == 2
    assert aud.sms_parts("س" * 134) == 2 and aud.sms_parts("س" * 135) == 3


# -- running --------------------------------------------------------------------------------


def test_run_sends_once_per_eligible_recipient(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    contact(rep, "customer", "مریم", "09121110001")
    contact(rep, "lead", "مریم (سرنخ)", "09121110001")
    contact(rep, "customer", "رضا", "09121110005")
    contact(rep, "customer", "بدون اجازه", "09121110002", consent=False)
    c = campaign(manager, everyone())
    started = manager.post(f"/campaigns/{c['id']}/start", json={}).json()
    assert started["status"] == "running" and started["stats"]["total"] == 4
    assert started["stats"]["pending"] == 2 and started["stats"]["skipped"] == 2
    tick()
    tick()  # repeating the step changes nothing
    messages = marketing_messages()
    assert sorted(m.recipient for m in messages) == ["+989121110001", "+989121110005"]
    assert all(m.campaign_id == uuid.UUID(c["id"]) for m in messages)
    assert any(m.body and m.body.startswith("رضا عزیز") for m in messages)
    rows = {r["name"]: r for r in recipients(manager, c["id"])}
    assert rows["مریم"]["status"] == "in_queue"
    assert rows["مریم (سرنخ)"]["reason"] == aud.DUPLICATE
    assert rows["بدون اجازه"]["reason"] == aud.NO_CONSENT
    # Once every message has a final status, the campaign is completed.
    with SessionLocal() as db:
        db.execute(update(OutboundMessage).values(status=MessageStatus.ACCEPTED))
        db.commit()
    tick()
    done = manager.get(f"/campaigns/{c['id']}").json()
    assert done["status"] == "completed" and done["stats"]["accepted"] == 2
    with SessionLocal() as db:
        assert db.scalar(select(Notification).where(Notification.user_id == org.manager.id))


def test_all_failed_means_failed(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    contact(rep, "customer", "مریم", "09121110001")
    c = campaign(manager, everyone())
    manager.post(f"/campaigns/{c['id']}/start", json={})
    tick()
    with SessionLocal() as db:
        db.execute(update(OutboundMessage).values(status=MessageStatus.FAILED))
        db.commit()
    tick()
    assert manager.get(f"/campaigns/{c['id']}").json()["status"] == "failed"


def test_consent_and_list_are_checked_again_before_sending(org: Org) -> None:
    """Criterion 10: withdrawing consent after the start, before sending, is respected."""
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    a = contact(rep, "customer", "الف", "09121110021")
    contact(rep, "customer", "بهار", "09121110022")
    contact(rep, "customer", "جواد", "09121110023")
    c = campaign(manager, everyone())
    manager.post(f"/campaigns/{c['id']}/start", json={})
    rep.patch(f"/customers/{a['id']}", json={"sms_consent": False})
    with SessionLocal() as db:
        db.add(Suppression(channel=Channel.SMS, address="+989121110022", reason="manual"))
        db.commit()
    tick()
    rows = {r["name"]: r for r in recipients(manager, c["id"])}
    assert rows["الف"]["reason"] == aud.NO_CONSENT
    assert rows["بهار"]["reason"] == aud.SUPPRESSED
    assert rows["جواد"]["status"] == "in_queue"


class _Refuse:
    """A provider that must not be called."""

    def send(self, *args: str) -> Accepted:
        raise AssertionError("sent despite the do-not-send list")


def test_unsubscribed_after_queueing_is_not_sent(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    contact(rep, "customer", "الف", "09121110031")
    c = campaign(manager, everyone())
    manager.post(f"/campaigns/{c['id']}/start", json={})
    tick()
    [message] = marketing_messages()
    with SessionLocal() as db:
        db.add(Suppression(channel=Channel.SMS, address=message.recipient, reason="unsubscribed"))
        db.commit()
    refuse = _Refuse()
    with SessionLocal() as db:
        process(db, get_redis(), Providers(sms=refuse, email=refuse), get_settings(), message.id)
    [message] = marketing_messages()
    assert message.status is MessageStatus.CANCELED


def test_pause_stops_unsent_and_resume_continues(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    for i in range(3):
        contact(rep, "customer", f"مخاطب {i}", f"0912111004{i}")
    c = campaign(manager, everyone())
    manager.post(f"/campaigns/{c['id']}/start", json={})
    tick()
    with SessionLocal() as db:  # one message already went out
        first = db.scalars(select(OutboundMessage).order_by(OutboundMessage.created_at)).first()
        assert first is not None
        first.status = MessageStatus.ACCEPTED
        db.commit()
    paused = manager.post(f"/campaigns/{c['id']}/pause").json()
    assert paused["status"] == "paused"
    assert paused["stats"]["pending"] == 2 and paused["stats"]["accepted"] == 1
    tick()  # a paused campaign queues nothing
    assert sum(m.status is MessageStatus.QUEUED for m in marketing_messages()) == 0
    manager.post(f"/campaigns/{c['id']}/resume")
    tick()
    live = [m for m in marketing_messages() if m.status is not MessageStatus.CANCELED]
    assert len(live) == 3 and len({m.recipient for m in live}) == 3


def test_window_daily_limit_and_budget(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    for i in range(3):
        contact(rep, "customer", f"مخاطب {i}", f"0912111005{i}")
    c = campaign(manager, everyone())
    manager.post(f"/campaigns/{c['id']}/start", json={})

    set_policy(window_start=time(9, 0), window_end=time(21, 0))
    night = datetime.now(TEHRAN).replace(hour=23, minute=0)
    tick(night)
    waiting = manager.get(f"/campaigns/{c['id']}").json()
    assert marketing_messages() == [] and "خارج از ساعت مجاز" in waiting["waiting_reason"]

    set_policy(window_start=time(0, 0), window_end=time(23, 59, 59), sms_daily_limit=1)
    tick()
    tick()  # the next step finds the day's limit reached
    assert len(marketing_messages()) == 1
    assert "سقف روزانه" in manager.get(f"/campaigns/{c['id']}").json()["waiting_reason"]

    set_policy(sms_daily_limit=100, sms_unit_price=1000, monthly_budget=2500)
    tick()  # two parts each: 2000 toman a message; one more fits, the third does not
    after = manager.get(f"/campaigns/{c['id']}").json()
    assert after["status"] == "paused" and "سقف مصرف" in after["waiting_reason"]
    assert after["stats"]["pending"] == 1 and len(marketing_messages()) == 2


def test_schedule_starts_later_and_pause_unschedules(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    contact(rep, "customer", "الف", "09121110061")
    c = campaign(manager, everyone())
    at = datetime.now(UTC) + timedelta(hours=2)
    scheduled = manager.post(f"/campaigns/{c['id']}/start", json={"scheduled_at": at.isoformat()})
    assert scheduled.json()["status"] == "scheduled" and scheduled.json()["stats"]["total"] == 0
    # The list is fixed when it runs: a contact added meanwhile is included.
    contact(rep, "customer", "بهار", "09121110062")
    tick()
    assert manager.get(f"/campaigns/{c['id']}").json()["status"] == "scheduled"
    tick(at + timedelta(minutes=1))
    running = manager.get(f"/campaigns/{c['id']}").json()
    assert running["status"] == "running" and running["stats"]["total"] == 2

    other = campaign(manager, everyone())
    manager.post(f"/campaigns/{other['id']}/start", json={"scheduled_at": at.isoformat()})
    back = manager.post(f"/campaigns/{other['id']}/pause").json()
    assert back["status"] == "draft" and back["scheduled_at"] is None


def test_start_needs_content_and_someone_to_reach(org: Org) -> None:
    manager = login_as(org.manager.id)
    empty = campaign(manager, everyone())
    r = manager.post(f"/campaigns/{empty['id']}/start", json={})
    assert r.status_code == 422 and "هیچ مخاطبی" in r.json()["detail"]
    contact(login_as(org.rep1.id), "customer", "الف", None, email="a@example.com")
    email = campaign(manager, everyone(), channel="email", subject="")
    r = manager.post(f"/campaigns/{email['id']}/start", json={})
    assert r.status_code == 422 and r.json()["detail"] == "موضوع ایمیل لازم است."


def test_test_send_goes_to_the_user(org: Org) -> None:
    manager = login_as(org.manager.id)
    c = campaign(manager, everyone())
    assert manager.post(f"/campaigns/{c['id']}/test").json() == {"to": "+989100000002"}
    with SessionLocal() as db:
        message = db.scalars(select(OutboundMessage)).one()
    assert message.purpose is Purpose.NOTIFICATION
    assert message.body and message.body.startswith("مدیر الف عزیز")


# -- unsubscribe ------------------------------------------------------------------------------


def test_unsubscribe_link(org: Org) -> None:
    manager, rep = login_as(org.manager.id), login_as(org.rep1.id)
    customer = contact(rep, "customer", "الف", "09121110071")
    lead = contact(rep, "lead", "الف (سرنخ)", "09121110071")
    c = campaign(manager, everyone())
    manager.post(f"/campaigns/{c['id']}/start", json={})
    tick()
    [message] = marketing_messages()
    assert message.body is not None
    token = message.body.rsplit("/u/", 1)[1]
    anonymous = TestClient(app)  # no session, no CSRF token: the link is the credential
    info = anonymous.get(f"/public/unsubscribe/{token}").json()
    assert info == {"channel": "sms", "address": "+98912•••071", "unsubscribed": False}
    assert anonymous.post(f"/public/unsubscribe/{token}").json()["unsubscribed"] is True
    assert anonymous.post(f"/public/unsubscribe/{token}").status_code == 200  # again: fine
    with SessionLocal() as db:
        assert db.scalar(select(Suppression).where(Suppression.address == "+989121110071"))
        assert db.get(Customer, uuid.UUID(customer["id"])).sms_consent is False  # type: ignore[union-attr]
        assert db.get(Lead, uuid.UUID(lead["id"])).sms_consent is False  # type: ignore[union-attr]
    assert anonymous.get(f"/public/unsubscribe/{token[:-1]}0").status_code == 404
    assert anonymous.get("/public/unsubscribe/nonsense").status_code == 404


def test_suppression_list_management(org: Org) -> None:
    manager, admin = login_as(org.manager.id), login_as(org.admin.id)
    r = manager.post("/suppressions", json={"channel": "sms", "address": "0912 111 0081"})
    assert r.status_code == 201 and r.json()["address"] == "+989121110081"
    dup = manager.post("/suppressions", json={"channel": "sms", "address": "09121110081"})
    assert dup.status_code == 409
    assert manager.delete(f"/suppressions/{r.json()['id']}").status_code == 403
    assert admin.delete(f"/suppressions/{r.json()['id']}").status_code == 204
    bad = manager.post("/suppressions", json={"channel": "email", "address": "not-an-email"})
    assert bad.status_code == 422


# -- access ---------------------------------------------------------------------------------------


def test_access(org: Org) -> None:
    manager = login_as(org.manager.id)
    c = campaign(manager, everyone())
    assert login_as(org.rep1.id).get("/campaigns").status_code == 403
    assert login_as(org.other_manager.id).get(f"/campaigns/{c['id']}").status_code == 404
    assert login_as(org.admin.id).get(f"/campaigns/{c['id']}").status_code == 200
    with SessionLocal() as db:
        team = Team(name="مالی", kind=TeamKind.FINANCE)
        db.add(team)
        db.flush()
        finance = User(full_name="مالی", mobile="+989100000099", role=Role.SALES_REP, team=team)
        db.add(finance)
        db.commit()
        finance_id = finance.id
    assert login_as(finance_id).get("/suppressions").status_code == 403
    policy = {
        "window_start": "08:00:00",
        "window_end": "20:00:00",
        "sms_daily_limit": 10,
        "email_daily_limit": 10,
        "sms_unit_price": 300,
        "email_unit_price": 0,
        "monthly_budget": None,
    }
    assert manager.put("/campaigns/policy", json=policy).status_code == 403
    saved = login_as(org.admin.id).put("/campaigns/policy", json=policy)
    assert saved.status_code == 200 and saved.json()["sms_unit_price"] == 300
    assert manager.get("/campaigns/policy").json()["window_start"] == "08:00:00"
    with SessionLocal() as db:
        assert db.get(MessagingPolicy, 1) is not None
    # Only drafts change.
    contact(login_as(org.rep1.id), "customer", "الف", "09121110091")
    assert manager.post(f"/campaigns/{c['id']}/start", json={}).status_code == 200
    edit = manager.put(
        f"/campaigns/{c['id']}", json={"name": "x y", "channel": "sms", "version": 1}
    )
    assert edit.status_code == 409
