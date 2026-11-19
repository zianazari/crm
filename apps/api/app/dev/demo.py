"""Demo data shaped like the approved design concepts (docs/images/designs): the same
companies, people and deals, a rising six-month sales trend, today's work, overdue
and unfollowed deals, a full sales record with its history, leads and tickets.

Everything is fictional. Dates are relative to today, so the demo always looks
current. ``reset`` first clears business data (customers, leads, deals, activities,
tickets, bookings, campaigns, notifications) and keeps users, teams, stages,
automations and settings. Development and staging only.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.dev.avatars import portrait
from app.modules.activities.models import (
    Activity,
    ActivityEvent,
    ActivityStatus,
    ActivityType,
    Note,
    Priority,
)
from app.modules.activities.service import tz
from app.modules.crm.models import (
    ContactChannel,
    Customer,
    CustomerOrganization,
    Lead,
    LeadSource,
    LeadStatus,
    Organization,
    Tag,
)
from app.modules.identity.models import Role, Team, User, UserAvatar
from app.modules.sales.models import Deal, DealHistory, DealStatus, Payment, PaymentKind, Stage
from app.modules.tickets.models import Ticket, TicketMessage, TicketStatus

MILLION = 1_000_000

# mobile, name, role, wears a scarf in the portrait, background, clothes
STAFF: list[tuple[str, str, Role, bool, tuple[int, int, int], tuple[int, int, int]]] = [
    ("+989120000002", "رضا کرمی", Role.SALES_MANAGER, False, (190, 214, 232), (52, 64, 84)),
    ("+989120000001", "سارا نیک‌پور", Role.SALES_REP, True, (226, 214, 236), (40, 44, 60)),
    ("+989120000011", "علی حیدری", Role.SALES_REP, False, (205, 228, 214), (70, 78, 96)),
    ("+989120000012", "مریم مرادی", Role.SALES_REP, True, (240, 222, 205), (34, 38, 52)),
    ("+989120000013", "مهدی رضایی", Role.SALES_REP, False, (214, 222, 240), (60, 70, 60)),
    ("+989120000014", "سارا محمدی", Role.SALES_REP, True, (212, 232, 228), (60, 40, 50)),
    ("+989120000015", "علی کاظمی", Role.SALES_REP, False, (236, 226, 206), (44, 54, 74)),
    ("+989120000016", "علی رضایی", Role.SALES_REP, False, (218, 230, 210), (36, 40, 48)),
]

# name, industry note, phone
ORGANIZATIONS = [
    ("شرکت آبان", "شرکت فناوری اطلاعات", "02188001234"),
    ("گروه سپهر", "خدمات مالی و سرمایه‌گذاری", "02122003344"),
    ("فروشگاه نارون", "خرده‌فروشی زنجیره‌ای", "02133005566"),
    ("شرکت آریا", "توزیع تجهیزات صنعتی", "02144007788"),
    ("شرکت پارس داده", "مرکز داده و میزبانی", "02166009900"),
    ("گروه صنعتی سایا", "تولید قطعات خودرو", "02155001122"),
    ("شرکت راهبرد نوین", "مشاوره مدیریت", "02126503040"),
    ("هلدینگ کاوه", "سرمایه‌گذاری و ساختمان", "02188776655"),
    ("شرکت دانش‌بنیان آوا", "نرم‌افزارهای آموزشی", "02191002030"),
    ("فروشگاه‌های ستاره", "خرده‌فروشی", "02177008090"),
    ("کلینیک سلامت آرین", "خدمات درمانی", "02122889900"),
    ("شرکت بهین‌سازان", "پیمانکاری ساختمان", "02136547890"),
]

# key, name, mobile, organization, owner, source, tags, days ago created, job title
CONTACTS: list[tuple[str, str, str, str | None, str, str, list[str], int, str | None]] = [
    (
        "aban",
        "سارا احمدی",
        "09121114567",
        "شرکت آبان",
        "علی رضایی",
        "معرفی",
        ["مشتری قدیمی"],
        420,
        "مدیر فروش",
    ),
    (
        "aban2",
        "کامران شریفی",
        "09121117788",
        "شرکت آبان",
        "علی حیدری",
        "معرفی",
        ["سازمانی"],
        70,
        "مدیر فناوری اطلاعات",
    ),
    (
        "sepehr",
        "نازنین فرهادی",
        "09122223344",
        "گروه سپهر",
        "مریم مرادی",
        "سایت",
        ["سازمانی"],
        210,
        "مدیر عملیات",
    ),
    (
        "naroon",
        "حمید صالحی",
        "09123335566",
        "فروشگاه نارون",
        "رضا کرمی",
        "تماس ورودی",
        [],
        160,
        "مدیر بازاریابی",
    ),
    (
        "naroon2",
        "لیلا کریمی",
        "09123336677",
        "فروشگاه نارون",
        "سارا نیک‌پور",
        "سایت",
        [],
        40,
        "مسئول خرید",
    ),
    (
        "arya",
        "بهرام توکلی",
        "09124447788",
        "شرکت آریا",
        "سارا نیک‌پور",
        "تبلیغ",
        ["VIP"],
        120,
        "مدیرعامل",
    ),
    (
        "arya2",
        "شیرین قاسمی",
        "09124448899",
        "شرکت آریا",
        "رضا کرمی",
        "شبکه اجتماعی",
        [],
        25,
        "کارشناس فروش",
    ),
    (
        "pars",
        "مهران یزدانی",
        "09125559900",
        "شرکت پارس داده",
        "مهدی رضایی",
        "معرفی",
        [],
        30,
        "مدیر پروژه",
    ),
    (
        "saya",
        "پریسا نوری",
        "09126661122",
        "گروه صنعتی سایا",
        "سارا محمدی",
        "سایت",
        ["سازمانی"],
        22,
        "مدیر خرید",
    ),
    (
        "rahbord",
        "امید جعفری",
        "09127772233",
        "شرکت راهبرد نوین",
        "علی کاظمی",
        "شبکه اجتماعی",
        [],
        18,
        "شریک",
    ),
    (
        "kaveh",
        "فرزانه اکبری",
        "09128883344",
        "هلدینگ کاوه",
        "علی حیدری",
        "معرفی",
        ["VIP"],
        15,
        "معاون مالی",
    ),
    (
        "ava",
        "کیوان رستمی",
        "09129994455",
        "شرکت دانش‌بنیان آوا",
        "مریم مرادی",
        "سایت",
        [],
        12,
        "مدیر محصول",
    ),
    (
        "setareh",
        "الهام منصوری",
        "09121235566",
        "فروشگاه‌های ستاره",
        "مهدی رضایی",
        "تبلیغ",
        [],
        9,
        "مدیر شعب",
    ),
    (
        "arian",
        "دکتر نیما شجاعی",
        "09121236677",
        "کلینیک سلامت آرین",
        "سارا محمدی",
        "تماس ورودی",
        [],
        6,
        "مدیر کلینیک",
    ),
    (
        "behin",
        "سعید ملکی",
        "09121237788",
        "شرکت بهین‌سازان",
        "علی کاظمی",
        "سایت",
        [],
        4,
        "مدیر اداری",
    ),
    ("person1", "رامین عباسی", "09121238899", None, "علی رضایی", "شبکه اجتماعی", [], 3, None),
    ("person2", "مینا حسینی", "09121239900", None, "سارا نیک‌پور", "سایت", [], 2, None),
]


@dataclass
class Ctx:
    db: Session
    now: datetime
    today: date
    users: dict[str, User]
    stages: list[Stage]
    customers: dict[str, Customer]
    orgs: dict[str, Organization]

    def at(self, days: int, hhmm: str) -> datetime:
        hours, minutes = (int(x) for x in hhmm.split(":"))
        moment = datetime.combine(self.today + timedelta(days=days), time(hours, minutes), tz())
        return moment.astimezone(UTC)


def _guard() -> None:
    if get_settings().environment not in {"development", "staging", "test"}:
        raise SystemExit("Demo data is only for development and staging.")


def _reset(db: Session) -> None:
    db.execute(
        text(
            "TRUNCATE customers, leads, organizations, deals, activities, notes, team_tasks, "
            "tickets, booking_links, bookings, campaigns, direct_messages, notifications, "
            "ownership_history, automation_events CASCADE"
        )
    )


def _staff(db: Session) -> dict[str, User]:
    manager = db.scalar(select(User).where(User.mobile == STAFF[0][0]))
    team = manager.team if manager and manager.team else None
    if team is None:
        team = db.scalar(select(Team).where(Team.name == "تیم فروش")) or Team(name="تیم فروش")
        db.add(team)
        db.flush()
    users: dict[str, User] = {}
    for i, (mobile, name, role, scarf, background, clothes) in enumerate(STAFF):
        user = db.scalar(select(User).where(User.mobile == mobile))
        if user is None:
            user = User(full_name=name, mobile=mobile, role=role, team_id=team.id)
            db.add(user)
            db.flush()
        user.full_name, user.is_active = name, True
        if role is Role.SALES_MANAGER:
            team.manager_id = user.id
        image = portrait(i + 3, scarf=scarf, background=background, clothes=clothes)
        avatar = db.get(UserAvatar, user.id)
        if avatar is None:
            db.add(UserAvatar(user_id=user.id, content=image, content_type="image/png"))
        else:
            avatar.content, avatar.content_type = image, "image/png"
        user.avatar_version = (user.avatar_version or 0) + 1
        users[name] = user
    admin = db.scalar(select(User).where(User.role == Role.ADMIN).order_by(User.created_at))
    if admin is not None:
        image = portrait(1, scarf=False, background=(220, 226, 236), clothes=(30, 34, 44))
        avatar = db.get(UserAvatar, admin.id)
        if avatar is None:
            db.add(UserAvatar(user_id=admin.id, content=image, content_type="image/png"))
        else:
            avatar.content = image
        admin.avatar_version = (admin.avatar_version or 0) + 1
        users["admin"] = admin
    db.flush()
    return users


def _named(db: Session, model: Any, name: str) -> Any:
    row = db.scalar(select(model).where(model.name == name))
    if row is None:
        row = model(name=name)
        db.add(row)
        db.flush()
    return row


def _people(c: Ctx) -> None:
    creator = c.users["رضا کرمی"]
    for name, note, phone in ORGANIZATIONS:
        org = Organization(name=name, phone=phone, created_by_id=creator.id)
        org.created_at = c.now - timedelta(days=400)
        c.db.add(org)
        c.orgs[name] = org
        _ = note
    c.db.flush()
    for key, name, mobile, org_name, owner, source, tags, days, job in CONTACTS:
        customer = Customer(
            full_name=name,
            mobile="+98" + mobile[1:],
            email=None,
            preferred_channel=ContactChannel.PHONE if days % 2 else ContactChannel.SMS,
            source_id=_named(c.db, LeadSource, source).id,
            owner_id=c.users[owner].id,
            created_by_id=c.users[owner].id,
            sms_consent=True,
            consent_updated_at=c.now - timedelta(days=days),
            description=(f"مخاطب اصلی {org_name} در پروژه‌های نرم‌افزاری." if org_name else None),
        )
        customer.tags = [_named(c.db, Tag, t) for t in tags]
        customer.created_at = c.now - timedelta(days=days, hours=3)
        c.db.add(customer)
        c.db.flush()
        if org_name:
            c.db.add(
                CustomerOrganization(
                    customer_id=customer.id, organization_id=c.orgs[org_name].id, job_title=job
                )
            )
        c.customers[key] = customer
    c.db.flush()


def _activity(
    c: Ctx,
    owner: str,
    kind: ActivityType,
    title: str,
    start: datetime | None,
    *,
    day: date | None = None,
    customer: Customer | None = None,
    deal: Deal | None = None,
    done: bool = False,
    outcome: str | None = None,
    description: str | None = None,
    duration: int | None = None,
    priority: Priority = Priority.NORMAL,
) -> Activity:
    user = c.users[owner]
    due = day or (start.astimezone(tz()).date() if start else c.today)
    activity = Activity(
        type=kind,
        title=title,
        description=description,
        owner_id=user.id,
        created_by_id=user.id,
        due_date=due,
        start_at=start,
        duration_minutes=duration if start else None,
        priority=priority,
        customer_id=customer.id if customer else (deal.customer_id if deal else None),
        deal_id=deal.id if deal else None,
        status=ActivityStatus.DONE if done else ActivityStatus.PENDING,
        outcome=outcome if done else None,
        completed_at=(start or c.now) + timedelta(minutes=duration or 20) if done else None,
        completed_by_id=user.id if done else None,
    )
    created = (start or c.now) - timedelta(days=2)
    activity.created_at = created
    # The timeline orders by the last change: completion for done work.
    activity.updated_at = activity.completed_at or created
    c.db.add(activity)
    c.db.flush()
    c.db.add(ActivityEvent(activity_id=activity.id, kind="created", actor_id=user.id, at=created))
    if activity.completed_at is not None:
        finished = activity.completed_at
        c.db.add(
            ActivityEvent(
                activity_id=activity.id,
                kind="completed",
                actor_id=user.id,
                at=finished,
            )
        )
        for record in (deal, customer):
            if record is not None and (
                record.last_activity_at is None or record.last_activity_at < finished
            ):
                record.last_activity_at = finished
    return activity


def _deal(
    c: Ctx,
    key: str,
    title: str,
    owner: str,
    amount: int,
    *,
    stage: int,
    created_days: int,
    won_days: int | None = None,
    lost: str | None = None,
    contract: int | None = None,
) -> Deal:
    customer = c.customers[key]
    link = c.db.scalar(
        select(CustomerOrganization).where(CustomerOrganization.customer_id == customer.id)
    )
    user = c.users[owner]
    created = c.now - timedelta(days=created_days, hours=2)
    status = (
        DealStatus.WON if won_days is not None else DealStatus.LOST if lost else DealStatus.OPEN
    )
    closed = (
        c.now - timedelta(days=won_days or 0, hours=5) if status is not DealStatus.OPEN else None
    )
    deal = Deal(
        title=title,
        customer_id=customer.id,
        organization_id=link.organization_id if link else None,
        owner_id=user.id,
        created_owner_id=user.id,
        closed_owner_id=user.id if closed else None,
        created_by_id=user.id,
        stage_id=c.stages[stage].id,
        status=status,
        amount=amount,
        contract_amount=(contract or amount) if status is DealStatus.WON else None,
        contract_date=closed.astimezone(tz()).date()
        if status is DealStatus.WON and closed
        else None,
        lost_reason=lost,
        closed_at=closed,
        closed_by_id=user.id if closed else None,
        expected_close_date=c.today + timedelta(days=20 + created_days % 25)
        if status is DealStatus.OPEN
        else None,
    )
    deal.created_at = created
    c.db.add(deal)
    c.db.flush()
    span = ((closed or c.now) - created) / (stage + 2)
    previous: uuid.UUID | None = None
    for i in range(stage + 1):
        c.db.add(
            DealHistory(
                deal_id=deal.id,
                from_stage_id=previous,
                to_stage_id=c.stages[i].id,
                from_status=DealStatus.OPEN if previous else None,
                to_status=DealStatus.OPEN,
                owner_id=user.id,
                changed_by_id=user.id,
                changed_at=created + span * i,
            )
        )
        previous = c.stages[i].id
    if closed:
        c.db.add(
            DealHistory(
                deal_id=deal.id,
                from_stage_id=previous,
                to_stage_id=deal.stage_id,
                from_status=DealStatus.OPEN,
                to_status=status,
                owner_id=user.id,
                changed_by_id=user.id,
                reason=lost,
                changed_at=closed,
            )
        )
    return deal


def _pay(c: Ctx, deal: Deal, share: float, days_after: int, ref: str) -> None:
    assert deal.contract_amount is not None and deal.contract_date is not None  # noqa: S101
    paid = deal.contract_date + timedelta(days=days_after)
    if paid > c.today:
        return
    payment = Payment(
        deal_id=deal.id,
        kind=PaymentKind.PAYMENT,
        amount=int(deal.contract_amount * share),
        paid_on=paid,
        reference=ref,
        recorded_by_id=deal.owner_id,
    )
    payment.created_at = datetime.combine(paid, time(11), tz()).astimezone(UTC)
    c.db.add(payment)


def _board(c: Ctx) -> None:
    """The sales board of the design, plus enough around it for a believable month."""
    call = ActivityType.CALL
    tomorrow = 1
    plan: list[tuple[str, str, str, int, int, int, tuple[int, str] | str | None]] = [
        # customer key, title, owner, amount (million), stage, days ago, next action
        ("aban2", "پیاده‌سازی CRM در شعب", "علی حیدری", 450, 0, 12, (tomorrow, "10:00")),
        ("sepehr", "مشاوره و نیازسنجی نرم‌افزار", "مریم مرادی", 300, 0, 9, (tomorrow, "14:00")),
        ("naroon", "بررسی راهکار باشگاه مشتریان", "رضا کرمی", 350, 0, 16, None),
        ("arya", "راهکار مدیریت فروش", "سارا نیک‌پور", 550, 1, 21, (tomorrow, "11:00")),
        ("aban2", "افزونه گزارش‌گیری پیشرفته", "علی حیدری", 300, 1, 18, (tomorrow, "16:00")),
        ("sepehr", "پیاده‌سازی و آموزش", "مریم مرادی", 420, 2, 26, "overdue"),
        ("arya2", "بسته سازمانی CRM", "رضا کرمی", 260, 2, 20, (tomorrow, "15:00")),
        ("naroon2", "خرید لایسنس سالانه", "سارا نیک‌پور", 390, 3, 33, (tomorrow, "12:00")),
        ("pars", "پاسخ به پیشنهاد قیمت", "مهدی رضایی", 210, 2, 14, None),
        ("saya", "هماهنگی جلسه نهایی", "سارا محمدی", 380, 3, 19, None),
        ("aban", "دریافت مدارک تکمیلی", "علی رضایی", 95, 1, 11, None),
        ("rahbord", "سامانه پشتیبانی مشتریان", "علی کاظمی", 175, 0, 5, (2, "09:30")),
        ("kaveh", "یکپارچه‌سازی با حسابداری", "علی حیدری", 640, 1, 13, (3, "11:30")),
        ("ava", "اپلیکیشن موبایل فروشندگان", "مریم مرادی", 280, 0, 7, (2, "13:00")),
        ("setareh", "باشگاه مشتریان ۲۰ شعبه", "مهدی رضایی", 520, 1, 8, (4, "10:30")),
        ("arian", "نوبت‌دهی و پیگیری بیماران", "سارا محمدی", 160, 0, 4, (1, "09:00")),
        ("behin", "مدیریت قراردادهای پیمانکاری", "علی کاظمی", 230, 0, 3, (3, "15:30")),
        ("person1", "اشتراک یک‌ساله نسخه پایه", "علی رضایی", 35, 0, 2, (2, "17:00")),
        ("person2", "مشاوره راه‌اندازی فروشگاه آنلاین", "سارا نیک‌پور", 45, 1, 6, (5, "12:30")),
        ("kaveh", "ماژول مدیریت اسناد", "رضا کرمی", 310, 2, 24, (6, "10:00")),
        ("saya", "پرتال تأمین‌کنندگان", "سارا محمدی", 470, 1, 17, (2, "14:30")),
        ("rahbord", "گزارش‌های مدیریتی", "علی کاظمی", 120, 2, 15, (1, "16:30")),
        ("ava", "تمدید پشتیبانی", "مریم مرادی", 90, 3, 28, (2, "10:00")),
    ]
    for key, title, owner, amount, stage, days, nxt in plan:
        deal = _deal(c, key, title, owner, amount * MILLION, stage=stage, created_days=days)
        customer = c.customers[key]
        _activity(
            c,
            owner,
            ActivityType.CALL,
            "تماس اولیه",
            c.at(-days, "11:15"),
            deal=deal,
            customer=customer,
            done=True,
            duration=20,
            outcome="نیازها و زمان‌بندی تصمیم‌گیری بررسی شد.",
        )
        if nxt == "overdue":
            _activity(
                c,
                owner,
                call,
                "پیگیری پیشنهاد قیمت",
                c.at(-1, "17:30"),
                deal=deal,
                customer=customer,
                priority=Priority.HIGH,
            )
        elif isinstance(nxt, tuple):
            _activity(
                c,
                owner,
                call,
                "تماس فردا" if nxt[0] == 1 else "تماس پیگیری",
                c.at(nxt[0], nxt[1]),
                deal=deal,
                customer=customer,
                duration=15,
            )


def _sales_history(c: Ctx) -> None:
    """Won deals over six months (a rising trend), a few lost ones, and payments."""
    wins: list[tuple[str, str, str, int, int]] = [
        # key, title, owner, million, days ago won
        ("aban2", "پیاده‌سازی کامل CRM", "علی حیدری", 600, 6),
        ("sepehr", "تمدید قرارداد و افزایش کاربر", "مریم مرادی", 320, 11),
        ("arya", "آموزش تیم فروش", "سارا نیک‌پور", 140, 3),
        ("kaveh", "مشاوره فرایند فروش", "رضا کرمی", 180, 33),
        ("naroon", "راه‌اندازی پنل پیامک", "رضا کرمی", 260, 38),
        ("pars", "مهاجرت داده‌ها", "مهدی رضایی", 290, 45),
        ("sepehr", "ماژول گزارش‌ساز", "مریم مرادی", 330, 64),
        ("arya2", "لایسنس ۲۵ کاربر", "رضا کرمی", 210, 70),
        ("aban2", "یکپارچه‌سازی ایمیل", "علی حیدری", 190, 76),
        ("saya", "پایلوت واحد فروش", "سارا محمدی", 250, 97),
        ("naroon2", "اپلیکیشن باشگاه", "سارا نیک‌پور", 230, 104),
        ("rahbord", "مشاوره پیاده‌سازی", "علی کاظمی", 140, 128),
        ("ava", "لایسنس آموزشی", "مریم مرادی", 210, 133),
        ("setareh", "پایلوت شعبه مرکزی", "مهدی رضایی", 125, 158),
        ("kaveh", "نسخه پایه", "علی حیدری", 160, 166),
    ]
    for i, (key, title, owner, million, days) in enumerate(wins):
        deal = _deal(
            c, key, title, owner, million * MILLION, stage=3, created_days=days + 40, won_days=days
        )
        # Most are paid in full, some in two installments, recent ones half, and every
        # fourth one not yet (so the unpaid balance has something to show).
        if i % 4 == 1:
            continue
        if days <= 30:
            _pay(c, deal, 0.5, 2, f"INV-{1400 + i}")
        elif i % 3 == 0:
            _pay(c, deal, 0.6, 5, f"INV-{1400 + i}")
            _pay(c, deal, 0.4, 30, f"INV-{1500 + i}")
        else:
            _pay(c, deal, 1.0, 5, f"INV-{1400 + i}")
    for key, title, owner, million, days, reason in [
        ("arian", "سامانه نوبت‌دهی آنلاین", "سارا محمدی", 110, 20, "قیمت بالاتر از بودجه"),
        ("behin", "پرتال پیمانکاران", "علی کاظمی", 200, 41, "انتخاب رقیب"),
        ("person1", "نسخه حرفه‌ای", "علی رضایی", 60, 9, "تعویق پروژه"),
    ]:
        _deal(c, key, title, owner, million * MILLION, stage=2, created_days=days + 30, lost=reason)


def _record(c: Ctx) -> None:
    """The sales record of design 3: شرکت آبان, contact سارا احمدی, owner علی رضایی."""
    customer = c.customers["aban"]
    for title, million, days in [("خرید لایسنس سالانه", 18, 560), ("خدمات راه‌اندازی", 12, 750)]:
        old = _deal(
            c,
            "aban",
            title,
            "علی رضایی",
            million * MILLION,
            stage=3,
            created_days=days + 30,
            won_days=days,
        )
        _pay(c, old, 1.0, 3, f"INV-{days}")
    deal = _deal(
        c,
        "aban",
        "ارتقای نسخه و آموزش کاربران",
        "علی رضایی",
        48 * MILLION,
        stage=2,
        created_days=12,
    )
    for kind, title, days, hhmm, outcome in [
        (
            ActivityType.CALL,
            "تماس اولیه",
            -9,
            "11:15",
            "اولین تماس با خانم سارا احمدی برقرار شد. نیازهای اولیه مشتری دریافت و قرار شد "
            "جلسه معرفی محصول برگزار شود.",
        ),
        (
            ActivityType.MEETING,
            "جلسه معرفی محصول",
            -5,
            "14:00",
            "جلسه آنلاین با خانم سارا احمدی برگزار شد. قابلیت‌های اصلی محصول معرفی و به "
            "سؤالات فنی پاسخ داده شد.",
        ),
        (
            ActivityType.TASK,
            "ارسال پیشنهاد قیمت",
            -4,
            "15:40",
            "پیشنهاد قیمت نهایی برای شرکت آبان ارسال شد. شامل جزئیات محصول، شرایط پرداخت و "
            "زمان‌بندی اجرا.",
        ),
    ]:
        _activity(
            c,
            "علی رضایی",
            kind,
            title,
            c.at(days, hhmm),
            deal=deal,
            customer=customer,
            done=True,
            outcome=outcome,
            duration=45 if kind is ActivityType.MEETING else 20,
        )
    _activity(
        c,
        "علی رضایی",
        ActivityType.CALL,
        "تماس پیگیری",
        c.at(1, "10:30"),
        deal=deal,
        customer=customer,
        duration=15,
        description="پیگیری دریافت بازخورد پیشنهاد قیمت و بررسی مراحل بعدی.",
    )
    note = Note(
        body="مشتری درخواست تخفیف برای پرداخت یکجا دارد؛ تا ۵٪ با تأیید مدیر ممکن است.",
        author_id=c.users["علی رضایی"].id,
        deal_id=deal.id,
        customer_id=customer.id,
    )
    note.created_at = c.at(-3, "09:20")
    c.db.add(note)


def _today(c: Ctx) -> None:
    """Today's activities, as on the overview (some done, one running late)."""
    for owner, kind, title, key, hhmm, done in [
        ("مهدی رضایی", ActivityType.CALL, "تماس با شرکت آبان", "aban2", "10:00", False),
        ("سارا محمدی", ActivityType.MEETING, "جلسه معرفی محصول", "saya", "14:00", False),
        ("علی کاظمی", ActivityType.FOLLOW_UP, "پیگیری پیشنهاد قیمت", "rahbord", "16:30", False),
        ("علی حیدری", ActivityType.CALL, "هماهنگی دمو با هلدینگ کاوه", "kaveh", "09:00", True),
        ("مریم مرادی", ActivityType.MEETING, "جلسه نیازسنجی گروه سپهر", "sepehr", "11:00", True),
        ("سارا نیک‌پور", ActivityType.CALL, "پیگیری قرارداد نارون", "naroon2", "12:30", False),
        ("رضا کرمی", ActivityType.MEETING, "بازبینی هفتگی فروش", "arya2", "13:00", False),
        ("علی رضایی", ActivityType.CALL, "تماس با رامین عباسی", "person1", "15:00", False),
        ("مهدی رضایی", ActivityType.TASK, "ارسال پیش‌فاکتور ستاره", "setareh", "15:30", False),
        ("سارا محمدی", ActivityType.CALL, "پیگیری کلینیک آرین", "arian", "17:00", False),
        ("علی کاظمی", ActivityType.CALL, "معرفی خدمات به بهین‌سازان", "behin", "11:30", True),
        ("مریم مرادی", ActivityType.FOLLOW_UP, "یادآوری تمدید آوا", "ava", "18:00", False),
    ]:
        _activity(
            c,
            owner,
            kind,
            title,
            c.at(0, hhmm),
            customer=c.customers[key],
            done=done,
            duration=30,
            outcome="انجام شد؛ جزئیات در پرونده ثبت شد." if done else None,
        )


def _leads(c: Ctx) -> None:
    for i, (name, company, owner, status, source, days) in enumerate(
        [
            ("حسین مختاری", "شرکت نیک‌اندیش", "علی حیدری", LeadStatus.NEW, "سایت", 0),
            ("سمیرا وکیلی", "آموزشگاه پویا", "سارا نیک‌پور", LeadStatus.NEW, "شبکه اجتماعی", 1),
            (
                "بابک زارعی",
                "شرکت ساختمانی آرمان",
                "مهدی رضایی",
                LeadStatus.WORKING,
                "تماس ورودی",
                3,
            ),
            ("نگین افشار", "فروشگاه گل‌سرخ", "مریم مرادی", LeadStatus.WORKING, "سایت", 5),
            ("پیمان سلطانی", "گروه لجستیک راه", "علی کاظمی", LeadStatus.QUALIFIED, "معرفی", 8),
            ("زهره کاظمی", "کافه‌های زنجیره‌ای دانه", "سارا محمدی", LeadStatus.NEW, "تبلیغ", 2),
            ("مجید فاضلی", "شرکت حمل‌ونقل سپید", "رضا کرمی", LeadStatus.DISQUALIFIED, "تبلیغ", 20),
            ("آرزو نادری", "استودیو طراحی نقش", "علی رضایی", LeadStatus.WORKING, "شبکه اجتماعی", 4),
        ]
    ):
        lead = Lead(
            full_name=name,
            mobile=f"+98912555{i:04d}",
            company_name=company,
            source_id=_named(c.db, LeadSource, source).id,
            owner_id=c.users[owner].id,
            created_by_id=c.users[owner].id,
            status=status,
            disqualify_reason="نیاز فعلی ندارد" if status is LeadStatus.DISQUALIFIED else None,
            last_contacted_at=c.now - timedelta(days=days // 2)
            if status is not LeadStatus.NEW
            else None,
        )
        lead.created_at = c.now - timedelta(days=days, hours=1)
        c.db.add(lead)


def _tickets(c: Ctx) -> None:
    for key, subject, owner, status, reply in [
        (
            "aban",
            "خطا در خروجی گزارش ماهانه",
            "علی رضایی",
            TicketStatus.IN_PROGRESS,
            "در حال بررسی هستیم؛ تا پایان روز نتیجه را اعلام می‌کنیم.",
        ),
        (
            "sepehr",
            "افزودن دو کاربر جدید",
            "مریم مرادی",
            TicketStatus.WAITING_CUSTOMER,
            "لطفاً نام و شماره همراه کاربران جدید را ارسال کنید.",
        ),
        ("naroon2", "سؤال درباره تمدید لایسنس", "سارا نیک‌پور", TicketStatus.NEW, None),
    ]:
        user = c.users[owner]
        opened = c.now - timedelta(days=2, hours=4)
        ticket = Ticket(
            customer_id=c.customers[key].id,
            subject=subject,
            status=status,
            assignee_id=user.id,
            opened_by_user_id=user.id,
            last_message_at=opened,
        )
        ticket.created_at = opened
        c.db.add(ticket)
        c.db.flush()
        first = TicketMessage(
            ticket_id=ticket.id,
            body=f"مشتری تلفنی اطلاع داد: {subject}.",
            author_user_id=user.id,
        )
        first.created_at = opened
        c.db.add(first)
        if reply:
            note = TicketMessage(
                ticket_id=ticket.id,
                body="موضوع به تیم فنی ارجاع شد.",
                internal=True,
                author_user_id=user.id,
            )
            note.created_at = opened + timedelta(hours=2)
            answer = TicketMessage(ticket_id=ticket.id, body=reply, author_user_id=user.id)
            answer.created_at = opened + timedelta(hours=3)
            ticket.last_message_at = answer.created_at
            c.db.add_all([note, answer])


def seed(reset: bool = False) -> None:
    _guard()
    import app.db.models  # noqa: F401 - every mapper, for the foreign keys
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        if reset:
            _reset(db)
        elif db.scalar(select(Organization.id).where(Organization.name == "شرکت آبان")):
            raise SystemExit("Demo data is already there. Use --reset to recreate it.")
        stages = list(
            db.scalars(select(Stage).where(Stage.is_active.is_(True)).order_by(Stage.sort_order))
        )
        if len(stages) < 4:
            raise SystemExit("Expected the four default sales stages.")
        now = datetime.now(UTC)
        c = Ctx(
            db=db,
            now=now,
            today=now.astimezone(tz()).date(),
            users=_staff(db),
            stages=stages,
            customers={},
            orgs={},
        )
        _people(c)
        _board(c)
        _sales_history(c)
        _record(c)
        _today(c)
        _leads(c)
        _tickets(c)
        db.commit()
        deals = db.scalar(select(func.count()).select_from(Deal))
        activities = db.scalar(select(func.count()).select_from(Activity))
        print(
            f"Demo data: {len(c.customers)} customers, {len(c.orgs)} organizations, "
            f"{deals} deals, {activities} activities."
        )
