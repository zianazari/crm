"""Availability and customer booking (spec 4.10; criterion 18)."""

import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.modules.activities.models import Activity, ActivityEvent
from app.modules.auth.deps import get_otp_sender
from app.modules.booking.models import Booking, BookingLink, BookingStatus
from app.modules.booking.service import send_customer_reminders
from app.modules.messaging.models import OutboundMessage, OutboxEvent
from app.modules.notifications.models import Notification, NotificationKind
from tests.conftest import Org, login_as
from tests.test_auth import CapturingSender
from tests.test_portal_tickets import customer, enable, portal_login

TEHRAN = ZoneInfo("Asia/Tehran")
EVERY_DAY = [{"weekday": d, "start": "08:00", "end": "20:00"} for d in range(7)]


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


def at(days: int, hhmm: str) -> datetime:
    """A moment in Tehran, ``days`` after today."""
    day = datetime.now(TEHRAN).date() + timedelta(days=days)
    hours, minutes = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(hours, minutes), TEHRAN).astimezone(UTC)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def open_calendar(client: TestClient, **overrides: Any) -> dict[str, Any]:
    """Every day 08:00-20:00, no notice, a week ahead, 10 minutes after each meeting."""
    body = {
        "buffer_before_minutes": 0,
        "buffer_after_minutes": 10,
        "min_notice_minutes": 0,
        "horizon_days": 7,
        "change_deadline_hours": 2,
        "rules": EVERY_DAY,
    } | overrides
    r = client.put("/booking/settings", json=body)
    assert r.status_code == 200, r.text
    return dict(r.json())


def meeting_type(client: TestClient) -> str:
    return str(client.get("/booking/settings").json()["meeting_types"][0]["id"])


def make_link(client: TestClient, customer_id: str, **extra: Any) -> dict[str, Any]:
    r = client.post(
        "/booking/links",
        json={"customer_id": customer_id, "meeting_type_id": meeting_type(client)} | extra,
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def token_of(created: dict[str, Any]) -> str:
    return str(created["url"].rsplit("/", 1)[1])


def slots_on(client: TestClient, token: str, days: int) -> list[datetime]:
    r = client.get(f"/book/{token}/slots")
    assert r.status_code == 200, r.text
    day = (datetime.now(TEHRAN).date() + timedelta(days=days)).isoformat()
    for entry in r.json()["days"]:
        if entry["date"] == day:
            return [datetime.fromisoformat(s) for s in entry["slots"]]
    return []


def verified(sender: CapturingSender, token: str, mobile: str = "09127778899") -> TestClient:
    client = TestClient(app)
    r = client.post(f"/book/{token}/otp/request", json={"channel": "sms", "destination": mobile})
    assert r.status_code == 202, r.text
    done = client.post(
        f"/book/{token}/otp/verify",
        json={"challenge_id": r.json()["challenge_id"], "code": sender.last_code},
    )
    assert done.status_code == 200, done.text
    assert done.json()["verified"] is True
    client.headers["X-CSRF-Token"] = client.cookies["crm_booking_csrf"]
    return client


# -- settings and free time --------------------------------------------------------------


def test_defaults_are_created_on_first_look(org: Org) -> None:
    settings = login_as(org.rep1.id).get("/booking/settings").json()
    assert settings["timezone"] == "Asia/Tehran"
    assert {r["weekday"] for r in settings["rules"]} == {0, 1, 2, 3, 4, 5}  # Friday off
    assert settings["meeting_types"][0]["duration_minutes"] == 30
    assert settings["change_deadline_hours"] == 24


def test_settings_reject_overlaps_and_only_managers_edit_others(org: Org) -> None:
    rep = login_as(org.rep1.id)
    overlapping = [
        {"weekday": 0, "start": "09:00", "end": "12:00"},
        {"weekday": 0, "start": "11:00", "end": "14:00"},
    ]
    assert open_calendar(rep)["horizon_days"] == 7
    r = rep.put(
        "/booking/settings",
        json=open_calendar(rep) | {"rules": overlapping},
    )
    assert r.status_code == 422
    assert (
        login_as(org.rep2.id)
        .get("/booking/settings", params={"user_id": str(org.rep1.id)})
        .status_code
        == 403
    )
    manager = login_as(org.manager.id)
    r = manager.get("/booking/settings", params={"user_id": str(org.rep1.id)})
    assert r.status_code == 200 and r.json()["user"]["id"] == str(org.rep1.id)
    assert (
        login_as(org.other_manager.id)
        .get("/booking/settings", params={"user_id": str(org.rep1.id)})
        .status_code
        == 403
    )


def test_timed_activities_bookings_and_days_off_block_time(org: Org) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    token = token_of(make_link(rep, customer(rep)))
    free = slots_on(rep, token, 2)
    assert free[0] == at(2, "08:00") and free[-1] == at(2, "19:30")
    day = (datetime.now(TEHRAN).date() + timedelta(days=2)).isoformat()
    # A timed call 10:00-10:45 blocks 10:00 and 10:30, and with the 10 minute buffer
    # after a meeting also 09:30; a task with only a due date blocks nothing.
    for body in (
        {
            "type": "call",
            "title": "تماس",
            "due_date": day,
            "start_time": "10:00",
            "duration_minutes": 45,
        },
        {"type": "task", "title": "ارسال قرارداد", "due_date": day},
    ):
        assert rep.post("/activities", json=body).status_code == 201
    free = slots_on(rep, token, 2)
    assert at(2, "09:00") in free
    for blocked in ("09:30", "10:00", "10:30"):
        assert at(2, blocked) not in free
    assert at(2, "11:00") in free

    leave = rep.post(
        "/booking/exceptions", json={"start_date": day, "end_date": day, "reason": "مرخصی"}
    )
    assert leave.status_code == 201
    assert slots_on(rep, token, 2) == []
    holiday = {"start_date": day, "end_date": day, "reason": "تعطیل رسمی", "organization": True}
    assert rep.post("/booking/exceptions", json=holiday).status_code == 403
    rep.delete(f"/booking/exceptions/{leave.json()['id']}")
    assert login_as(org.admin.id).post("/booking/exceptions", json=holiday).status_code == 201
    assert slots_on(rep, token, 2) == []


def test_minimum_notice_and_horizon(org: Org) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep, min_notice_minutes=2 * 24 * 60, horizon_days=3)
    token = token_of(make_link(rep, customer(rep)))
    assert slots_on(rep, token, 1) == []
    assert slots_on(rep, token, 3) != []
    assert slots_on(rep, token, 4) == []


# -- links ------------------------------------------------------------------------------------


def test_who_may_make_a_link(org: Org) -> None:
    rep = login_as(org.rep1.id)
    customer_id = customer(rep)
    mine = meeting_type(rep)
    other = login_as(org.rep2.id)
    body = {"customer_id": customer_id, "meeting_type_id": mine}
    assert other.post("/booking/links", json=body).status_code == 403  # not their customer
    other_customer = customer(other, "سارا", "09125550000")
    r = rep.post("/booking/links", json=body | {"customer_id": other_customer})
    assert r.status_code == 403
    # A manager can send a link into a team member's calendar.
    r = login_as(org.manager.id).post("/booking/links", json=body)
    assert r.status_code == 201 and r.json()["link"]["user"]["id"] == str(org.rep1.id)
    assert rep.post("/booking/links", json=body | {"send": "email"}).status_code == 422


def test_link_is_sent_and_shows_nothing_of_the_record(org: Org) -> None:
    rep = login_as(org.rep1.id)
    created = make_link(rep, customer(rep), send="sms")
    assert created["link"]["state"] == "open" and created["link"]["sent_via"] == "sms"
    with SessionLocal() as db:
        message = db.scalar(select(OutboundMessage))
        assert message is not None and message.recipient == "+989127778899"
        assert created["url"] in (message.body or "")
        stored = db.scalar(select(BookingLink))
        assert stored is not None and token_of(created) not in stored.token_hash
    page = TestClient(app).get(f"/book/{token_of(created)}")
    assert page.status_code == 200
    body = page.text
    assert "مریم" not in body and "+98912" not in body
    assert page.json()["staff_name"] == "کارشناس ۱" and page.json()["booking"] is None
    assert TestClient(app).get("/book/not-a-real-token").status_code == 404


def test_expired_and_revoked_links_are_refused(org: Org) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    created = make_link(rep, customer(rep))
    token = token_of(created)
    with SessionLocal() as db:
        link = db.get(BookingLink, uuid.UUID(created["link"]["id"]))
        assert link is not None
        link.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    anonymous = TestClient(app)
    assert anonymous.get(f"/book/{token}").json()["state"] == "expired"
    assert anonymous.get(f"/book/{token}/slots").status_code == 410
    second = token_of(make_link(rep, customer(rep, "علی", "09121234567")))
    rep.post(f"/booking/links/{created['link']['id']}/revoke")
    assert anonymous.get(f"/book/{second}/slots").status_code == 200
    revoked = rep.get("/booking/links", params={"customer_id": created["link"]["customer"]["id"]})
    assert revoked.json()[0]["state"] == "revoked"


# -- booking --------------------------------------------------------------------------------


def test_booking_needs_verification_with_the_customers_own_address(
    org: Org, sender: CapturingSender
) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    token = token_of(make_link(rep, customer(rep)))
    stranger = TestClient(app)
    r = stranger.post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))})
    assert r.status_code == 401
    r = stranger.post(
        f"/book/{token}/otp/request", json={"channel": "sms", "destination": "09120001111"}
    )
    assert r.status_code == 202 and sender.sent == []  # not this customer's number
    client = verified(sender, token)
    no_csrf = TestClient(app, cookies=client.cookies)
    r = no_csrf.post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))})
    assert r.status_code == 403
    # The verification is bound to its link.
    other = token_of(make_link(rep, customer(rep, "علی", "09121234567")))
    r = client.post(f"/book/{other}/book", json={"start_at": iso(at(2, "10:00"))})
    assert r.status_code == 401


def test_booking_creates_the_meeting_and_tells_both_sides(
    org: Org, sender: CapturingSender
) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    customer_id = customer(rep)
    deal = rep.post("/deals", json={"customer_id": customer_id, "title": "قرارداد سالانه"})
    assert deal.status_code == 201, deal.text
    token = token_of(make_link(rep, customer_id, deal_id=deal.json()["id"]))
    client = verified(sender, token)
    r = client.post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))})
    assert r.status_code == 201, r.text
    view = r.json()
    assert view["state"] == "booked" and view["booking"]["can_change"] is True
    assert datetime.fromisoformat(view["booking"]["start_at"]) == at(2, "10:00")

    with SessionLocal() as db:
        booking = db.scalar(select(Booking))
        assert booking is not None
        activity = db.get(Activity, booking.activity_id)
        assert activity is not None
        assert activity.type.value == "meeting" and activity.owner_id == org.rep1.id
        assert str(activity.customer_id) == customer_id
        assert str(activity.deal_id) == deal.json()["id"]
        assert activity.start_at == at(2, "10:00") and activity.duration_minutes == 30
        assert activity.remind_at is not None
        event = db.scalar(select(ActivityEvent).where(ActivityEvent.activity_id == activity.id))
        assert event is not None and event.actor_id is None
        assert (event.details or {}).get("by") == "customer"
        notes = list(db.scalars(select(Notification).where(Notification.user_id == org.rep1.id)))
        assert [n.kind for n in notes] == [NotificationKind.BOOKING]
        confirmation = db.scalar(
            select(OutboundMessage).order_by(OutboundMessage.created_at.desc())
        )
        assert confirmation is not None and "ثبت شد" in (confirmation.body or "")

    # The slot (and the 10 minutes after it) is gone for everyone; one booking per link.
    free = slots_on(rep, token_of(make_link(rep, customer_id)), 2)
    assert at(2, "10:00") not in free and at(2, "10:30") in free
    r = client.post(f"/book/{token}/book", json={"start_at": iso(at(2, "12:00"))})
    assert r.status_code == 409
    assert rep.get("/activities", params={"customer_id": customer_id}).json()["total"] >= 1


def test_a_taken_or_invented_time_is_refused(org: Org, sender: CapturingSender) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    first = token_of(make_link(rep, customer(rep)))
    second = token_of(make_link(rep, customer(rep, "علی", "09121234567")))
    a = verified(sender, first)
    get_redis().delete(*get_redis().keys("otp:rl:ip:*"))
    b = verified(sender, second, "09121234567")
    assert a.post(f"/book/{first}/book", json={"start_at": iso(at(2, "10:00"))}).status_code == 201
    r = b.post(f"/book/{second}/book", json={"start_at": iso(at(2, "10:00"))})
    assert r.status_code == 409 and "آزاد" in r.json()["detail"]
    off_grid = b.post(f"/book/{second}/book", json={"start_at": iso(at(2, "10:10"))})
    assert off_grid.status_code == 409
    night = b.post(f"/book/{second}/book", json={"start_at": iso(at(2, "22:00"))})
    assert night.status_code == 409


def test_simultaneous_bookings_of_one_slot_make_one_booking(
    org: Org, sender: CapturingSender
) -> None:
    """Criterion 18: two requests at once for one person and time, one booking."""
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    mobiles = ["09127778899", "09121234567", "09123334444", "09125556666"]
    tokens, clients = [], []
    for i, mobile in enumerate(mobiles):
        token = token_of(make_link(rep, customer(rep, f"مشتری {i}", mobile)))
        get_redis().delete(*(get_redis().keys("otp:rl:ip:*") or ["none"]))
        tokens.append(token)
        clients.append(verified(sender, token, mobile))
    barrier = threading.Barrier(len(tokens))
    codes: list[int] = []

    def attempt(client: TestClient, token: str) -> None:
        barrier.wait()
        r = client.post(f"/book/{token}/book", json={"start_at": iso(at(3, "11:00"))})
        codes.append(r.status_code)

    threads = [
        threading.Thread(target=attempt, args=pair) for pair in zip(clients, tokens, strict=True)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [201, 409, 409, 409]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Booking)))) == 1


def test_overlapping_confirmed_bookings_are_impossible_in_the_database(
    org: Org, sender: CapturingSender
) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    token = token_of(make_link(rep, customer(rep)))
    client = verified(sender, token)
    client.post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))})
    with SessionLocal() as db:
        booking = db.scalar(select(Booking))
        assert booking is not None
        copy = Booking(
            link_id=booking.link_id,
            user_id=booking.user_id,
            customer_id=booking.customer_id,
            meeting_type_id=booking.meeting_type_id,
            activity_id=booking.activity_id,
            start_at=booking.start_at + timedelta(minutes=15),
            end_at=booking.end_at + timedelta(minutes=15),
            contact_channel=booking.contact_channel,
            contact_address=booking.contact_address,
        )
        db.add(copy)
        with pytest.raises(IntegrityError):
            db.commit()


def test_customer_moves_and_cancels_within_the_deadline(org: Org, sender: CapturingSender) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    customer_id = customer(rep)
    token = token_of(make_link(rep, customer_id))
    client = verified(sender, token)
    client.post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))})
    # The current time is offered again when moving, next to the others.
    assert at(2, "10:00") in slots_on(client, token, 2)
    r = client.post(f"/book/{token}/reschedule", json={"start_at": iso(at(2, "10:30"))})
    assert r.status_code == 200, r.text
    assert datetime.fromisoformat(r.json()["booking"]["start_at"]) == at(2, "10:30")
    with SessionLocal() as db:
        rows = {b.status: b for b in db.scalars(select(Booking))}
        old, new = rows[BookingStatus.RESCHEDULED], rows[BookingStatus.CONFIRMED]
        assert old.rescheduled_to_id == new.id and old.activity_id == new.activity_id
        activity = db.get(Activity, new.activity_id)
        assert activity is not None and activity.start_at == at(2, "10:30")
        kinds = [e.kind for e in db.scalars(select(ActivityEvent).order_by(ActivityEvent.at))]
        assert kinds == ["created", "rescheduled"]
    r = client.post(f"/book/{token}/cancel", json={"reason": "سفر کاری پیش آمد"})
    assert r.status_code == 200 and r.json()["state"] == "open"
    with SessionLocal() as db:
        activity = db.get(Activity, new.activity_id)
        assert activity is not None and activity.status.value == "canceled"
        assert "مشتری" in (activity.cancel_reason or "")
    assert at(2, "10:30") in slots_on(rep, token, 2)
    # After canceling, the same link can book again.
    r = client.post(f"/book/{token}/book", json={"start_at": iso(at(2, "11:00"))})
    assert r.status_code == 201


def test_changes_close_at_the_deadline(org: Org, sender: CapturingSender) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep, change_deadline_hours=24 * 14)
    token = token_of(make_link(rep, customer(rep)))
    client = verified(sender, token)
    view = client.post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))}).json()
    assert view["booking"]["can_change"] is False
    assert client.post(f"/book/{token}/cancel", json={}).status_code == 409
    r = client.post(f"/book/{token}/reschedule", json={"start_at": iso(at(2, "12:00"))})
    assert r.status_code == 409


def test_staff_cancel_frees_the_time_and_cannot_move_a_booked_meeting(
    org: Org, sender: CapturingSender
) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    customer_id = customer(rep)
    token = token_of(make_link(rep, customer_id))
    verified(sender, token).post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))})
    with SessionLocal() as db:
        booking = db.scalar(select(Booking))
        assert booking is not None
        activity = db.get(Activity, booking.activity_id)
        assert activity is not None
        activity_id, version = activity.id, activity.version
    r = rep.post(
        f"/activities/{activity_id}/postpone",
        json={"version": version, "due_date": at(3, "10:00").date().isoformat(), "reason": "x"},
    )
    assert r.status_code == 409
    r = rep.patch(f"/activities/{activity_id}", json={"version": version, "title": "جلسه معرفی"})
    assert r.status_code == 200  # the title is fine
    r = rep.post(
        f"/activities/{activity_id}/cancel",
        json={"version": r.json()["version"], "reason": "کارشناس بیمار است"},
    )
    assert r.status_code == 200
    listed = rep.get("/booking/bookings", params={"customer_id": customer_id}).json()
    assert listed[0]["status"] == "canceled" and listed[0]["canceled_by"]["id"] == str(org.rep1.id)
    with SessionLocal() as db:
        last = db.scalar(select(OutboundMessage).order_by(OutboundMessage.created_at.desc()))
        assert last is not None and "لغو شد" in (last.body or "")
    assert at(2, "10:00") in slots_on(rep, token, 2)


def test_portal_session_verifies_and_lists_only_own_bookings(
    org: Org, sender: CapturingSender
) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    mine = customer(rep)
    enable(rep, mine)
    other = customer(rep, "علی", "09121234567")
    portal = portal_login(sender)
    token = token_of(make_link(rep, mine))
    assert portal.get(f"/book/{token}").json()["verified"] is True
    r = portal.post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))})
    assert r.status_code == 201, r.text
    other_token = token_of(make_link(rep, other))
    assert portal.get(f"/book/{other_token}").json()["verified"] is False

    listed = portal.get("/portal/bookings").json()
    assert len(listed) == 1 and listed[0]["staff_name"] == "کارشناس ۱"
    booking_id = listed[0]["id"]
    assert portal.get(f"/portal/bookings/{booking_id}/slots").status_code == 200
    r = portal.post(
        f"/portal/bookings/{booking_id}/reschedule", json={"start_at": iso(at(2, "13:00"))}
    )
    assert r.status_code == 200 and r.json()["id"] != booking_id
    # Someone else's booking, by id: nothing.
    get_redis().delete(*get_redis().keys("otp:rl:ip:*"))
    other_client = verified(sender, other_token, "09121234567")
    other_client.post(f"/book/{other_token}/book", json={"start_at": iso(at(2, "15:00"))})
    with SessionLocal() as db:
        theirs = db.scalar(select(Booking).where(Booking.customer_id == uuid.UUID(other)))
        assert theirs is not None
    assert portal.post(f"/portal/bookings/{theirs.id}/cancel", json={}).status_code == 404
    assert portal.get(f"/portal/bookings/{theirs.id}/slots").status_code == 404
    assert len(portal.get("/portal/bookings").json()) == 1


def test_customer_reminder_a_day_before(org: Org, sender: CapturingSender) -> None:
    rep = login_as(org.rep1.id)
    open_calendar(rep)
    token = token_of(make_link(rep, customer(rep)))
    verified(sender, token).post(f"/book/{token}/book", json={"start_at": iso(at(2, "10:00"))})
    with SessionLocal() as db:
        booking = db.scalar(select(Booking))
        assert booking is not None
        assert send_customer_reminders(db, booking.start_at - timedelta(hours=30)) == 0
        assert send_customer_reminders(db, booking.start_at - timedelta(hours=20)) == 1
        db.commit()
        assert send_customer_reminders(db, booking.start_at - timedelta(hours=19)) == 0
        last = db.scalar(select(OutboundMessage).order_by(OutboundMessage.created_at.desc()))
        assert last is not None and (last.body or "").startswith("یادآوری")
