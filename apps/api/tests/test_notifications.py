"""In-app notifications: reminders, digest, assignments and the API (spec 4.2, 5, 7)."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text

from app.db.session import SessionLocal
from app.modules.activities.models import Activity
from app.modules.notifications.models import Notification, NotificationKind
from app.modules.notifications.scheduler import ADVISORY_LOCK, send_daily_digest, tick
from tests.conftest import Org, login_as
from tests.test_deals import make_customer, make_deal

TZ = ZoneInfo("Asia/Tehran")
DAY = date(2030, 1, 15)


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), TZ).astimezone(UTC)


def create_activity(client: Any, **fields: Any) -> dict[str, Any]:
    body = {"type": "call", "title": "تماس پیگیری", "due_date": DAY.isoformat(), **fields}
    r = client.post("/activities", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def remind_at(activity_id: str) -> datetime | None:
    with SessionLocal() as db:
        activity = db.get(Activity, activity_id)
        assert activity is not None
        return activity.remind_at


def notifications(user_id: Any, kind: NotificationKind | None = None) -> list[Notification]:
    with SessionLocal() as db:
        query = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at)
        )
        if kind is not None:
            query = query.where(Notification.kind == kind)
        return list(db.scalars(query))


def run_tick(now: datetime) -> bool:
    with SessionLocal() as db:
        return tick(db, now)


# -- reminder time ------------------------------------------------------------------


def test_reminder_time_follows_start_or_nine_oclock(org: Org) -> None:
    rep = login_as(org.rep1.id)
    timed = create_activity(rep, start_time="10:30", reminder_minutes=15)
    untimed = create_activity(rep, reminder_minutes=0)
    none = create_activity(rep)
    assert remind_at(timed["id"]) == local(DAY, 10, 15)
    assert remind_at(untimed["id"]) == local(DAY, 9)
    assert remind_at(none["id"]) is None


def test_rescheduling_rearms_the_reminder(org: Org) -> None:
    rep = login_as(org.rep1.id)
    activity = create_activity(rep, start_time="10:00", reminder_minutes=60)
    assert run_tick(local(DAY, 9, 1))
    assert len(notifications(org.rep1.id, NotificationKind.ACTIVITY_REMINDER)) == 1

    later = DAY + timedelta(days=1)
    rep.post(
        f"/activities/{activity['id']}/postpone",
        json={"due_date": later.isoformat(), "start_time": "10:00", "version": activity["version"]},
    )
    assert remind_at(activity["id"]) == local(later, 9)
    run_tick(local(later, 9, 1))
    assert len(notifications(org.rep1.id, NotificationKind.ACTIVITY_REMINDER)) == 2


# -- scheduler ------------------------------------------------------------------------


def test_due_reminder_is_sent_once_with_a_link(org: Org) -> None:
    rep = login_as(org.rep1.id)
    deal = make_deal(rep, make_customer(rep))
    create_activity(rep, deal_id=deal["id"], start_time="11:00", reminder_minutes=30)
    future = create_activity(rep, title="بعدا", start_time="16:00", reminder_minutes=15)
    done = create_activity(rep, title="انجام‌شده", start_time="10:00", reminder_minutes=15)
    rep.post(f"/activities/{done['id']}/complete", json={"outcome": "انجام شد", "version": 1})

    now = local(DAY, 10, 31)
    run_tick(now)
    run_tick(now + timedelta(seconds=30))  # a repeated tick sends nothing new
    [reminder] = notifications(org.rep1.id, NotificationKind.ACTIVITY_REMINDER)
    assert reminder.title.startswith("یادآوری تماس") and reminder.link == f"/deals/{deal['id']}"
    assert (
        reminder.body is not None and "۱۱:۰۰" in reminder.body and "پیاده‌سازی CRM" in reminder.body
    )
    assert remind_at(future["id"]) is not None


def test_stale_reminders_are_dropped_not_sent_late(org: Org) -> None:
    rep = login_as(org.rep1.id)
    activity = create_activity(rep, start_time="10:00", reminder_minutes=0)
    run_tick(local(DAY + timedelta(days=2), 10))
    assert notifications(org.rep1.id, NotificationKind.ACTIVITY_REMINDER) == []
    with SessionLocal() as db:
        assert db.get(Activity, activity["id"]).reminded_at is not None  # type: ignore[union-attr]


def test_only_one_scheduler_runs_at_a_time() -> None:
    with SessionLocal() as holder:
        holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": ADVISORY_LOCK})
        try:
            assert run_tick(datetime.now(UTC)) is False
        finally:
            holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK})


def test_daily_digest_after_eight_once_per_day(org: Org) -> None:
    rep = login_as(org.rep1.id)
    create_activity(rep, title="امروز")
    create_activity(rep, title="دیروز", due_date=(DAY - timedelta(days=1)).isoformat())
    with SessionLocal() as db:
        assert send_daily_digest(db, local(DAY, 7, 59)) == 0
        db.commit()
    run_tick(local(DAY, 8, 1))
    run_tick(local(DAY, 12))
    [digest] = notifications(org.rep1.id, NotificationKind.DAILY_DIGEST)
    assert digest.title == "برنامه امروز: ۱ کار امروز و ۱ کار معوق"
    assert notifications(org.rep2.id, NotificationKind.DAILY_DIGEST) == []


# -- assignment ------------------------------------------------------------------------


def test_assignments_by_someone_else_notify_the_new_owner(org: Org) -> None:
    manager, rep1 = login_as(org.manager.id), login_as(org.rep1.id)
    create_activity(manager, title="پیگیری مالی", owner_id=str(org.rep1.id))
    create_activity(rep1, title="کار خودم")
    [assigned] = notifications(org.rep1.id, NotificationKind.ACTIVITY_ASSIGNED)
    assert "پیگیری مالی" in assigned.title and assigned.body == "توسط مدیر الف"

    lead = rep1.post("/leads", json={"full_name": "علی رضایی", "mobile": "09121111111"}).json()
    manager.post(
        f"/leads/{lead['id']}/assign", json={"owner_id": str(org.rep2.id), "reason": "تقسیم کار"}
    )
    [record] = notifications(org.rep2.id, NotificationKind.RECORD_ASSIGNED)
    assert record.link == f"/leads/{lead['id']}" and "تقسیم کار" in (record.body or "")


def test_transfer_on_deactivation_notifies_once(org: Org) -> None:
    rep1 = login_as(org.rep1.id)
    make_deal(rep1, make_customer(rep1))
    login_as(org.admin.id).post(
        f"/users/{org.rep1.id}/deactivate", json={"transfer_to_id": str(org.rep2.id)}
    )
    [note] = notifications(org.rep2.id, NotificationKind.RECORD_ASSIGNED)
    assert "کارشناس ۱" in note.title and "۱ فروش باز" in (note.body or "")


# -- API ----------------------------------------------------------------------------


def test_users_see_and_mark_only_their_own(org: Org) -> None:
    manager = login_as(org.manager.id)
    for title in ("یک", "دو"):
        create_activity(manager, title=title, owner_id=str(org.rep1.id))
    rep1, rep2 = login_as(org.rep1.id), login_as(org.rep2.id)

    page = rep1.get("/notifications").json()
    assert page["unread"] == 2 and len(page["items"]) == 2
    assert rep2.get("/notifications").json()["items"] == []

    first = page["items"][0]["id"]
    assert rep2.post(f"/notifications/{first}/read").status_code == 404
    assert rep1.post(f"/notifications/{first}/read").status_code == 204
    assert rep1.get("/notifications/unread-count").json() == {"unread": 1}
    assert [
        n["id"] for n in rep1.get("/notifications", params={"unread_only": True}).json()["items"]
    ] != [first]
    rep1.post("/notifications/read-all")
    assert rep1.get("/notifications/unread-count").json() == {"unread": 0}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 2
