"""Overview and reports (spec 4.4 and section 0, decision 2).

Definitions, kept identical across endpoints:

* Sales ("فروش") = won deals by **contract date**, attributed to the owner at closing.
* Inbound deals = deals by **creation date**, attributed to the owner at creation; the
  status split is the status today (the evaluation date).
* Received = payments minus refunds by **payment date**, voided entries excluded.
  Never mixed with sales or with the unpaid balance.
* Unpaid balance = contract amount minus net received, for won deals, as of now.
* Win rate = won / (won + lost) among deals **closed** in the period; null when no
  deal closed (shown as "—", never as 0 %).
* Lead conversion = leads **created** in the period whose customer reached a first won
  deal by the evaluation date (the end of the period, or today if earlier).

Every figure is limited to the records the user sees in full (admin: all, manager:
their team, rep: their own), so aggregates never reveal other people's amounts.
"""

import statistics
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import (
    ColumnElement,
    Date,
    and_,
    case,
    cast,
    exists,
    func,
    literal_column,
    select,
    true,
)
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.core.config import get_settings
from app.modules.activities.models import OPEN_STATUSES, Activity, ActivityStatus, ActivityType
from app.modules.activities.schemas import ActivityBrief
from app.modules.activities.service import next_activities, today
from app.modules.auth.deps import DbDep, require_csrf
from app.modules.crm.access import AccessScope
from app.modules.crm.common import ScopeDep, day_bounds, require_sales_access, unprocessable
from app.modules.crm.models import Customer, Lead, LeadSource
from app.modules.crm.schemas import UserRef
from app.modules.identity.models import Team, User
from app.modules.sales.models import Deal, DealStatus, Payment, PaymentKind, Stage

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_csrf), Depends(require_sales_access)],
)

CURRENCY = "IRT"


# -- filters -----------------------------------------------------------------


class Filters:
    """Shared query filters: period, person, team, source — always inside the user's scope."""

    def __init__(
        self,
        db: DbDep,
        scope: ScopeDep,
        date_from: date,
        date_to: date,
        owner_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
        source_id: uuid.UUID | None = None,
    ) -> None:
        if date_from > date_to:
            raise unprocessable("تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد.")
        self.db = db
        self.scope = scope
        self.date_from = date_from
        self.date_to = date_to
        self.start, self.end = day_bounds(date_from, date_to)
        self.source_id = source_id
        self.owners = _owners(db, scope, owner_id, team_id)
        # Statuses are as of today; the evaluation date never lies in the future.
        self.evaluated_on = min(date_to, today())

    def owner(
        self, column: InstrumentedAttribute[uuid.UUID] | InstrumentedAttribute[uuid.UUID | None]
    ) -> ColumnElement[bool]:
        return true() if self.owners is None else column.in_(self.owners)

    def customer_source(self) -> ColumnElement[bool]:
        """Deals by the acquisition source of their customer."""
        if self.source_id is None:
            return true()
        return Deal.customer_id.in_(select(Customer.id).where(Customer.source_id == self.source_id))


FiltersDep = Annotated[Filters, Depends()]


def _owners(
    db: Session, scope: AccessScope, owner_id: uuid.UUID | None, team_id: uuid.UUID | None
) -> set[uuid.UUID] | None:
    allowed = scope.owner_ids()
    selected = allowed
    if team_id is not None:
        team = db.get(Team, team_id)
        if team is None:
            raise unprocessable("تیم معتبر نیست.")
        members = set(db.scalars(select(User.id).where(User.team_id == team.id)))
        if team.manager_id:
            members.add(team.manager_id)
        selected = members if allowed is None else members & allowed
    if owner_id is not None:
        if allowed is not None and owner_id not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="گزارش این کاربر در دسترس شما نیست."
            )
        selected = {owner_id} if selected is None else ({owner_id} & selected)
    return selected


def local_date(column: InstrumentedAttribute[datetime]) -> ColumnElement[date]:
    """A timestamp's calendar date in the organization's time zone."""
    return cast(func.timezone(get_settings().timezone, column), Date)


SIGNED_PAYMENT = case((Payment.kind == PaymentKind.REFUND, -Payment.amount), else_=Payment.amount)


# -- summary -----------------------------------------------------------------


class Money(BaseModel):
    count: int
    amount: int


class Rate(BaseModel):
    numerator: int
    denominator: int
    rate: float | None


class Summary(BaseModel):
    currency: str
    date_from: date
    date_to: date
    evaluated_on: date
    sales: Money
    received: int
    unpaid_balance: int
    pipeline: Money
    new_leads: int
    new_customers: int
    first_purchase_customers: int
    win_rate: Rate
    lead_conversion: Rate
    first_contact_median_hours: float | None
    overdue_activities: int
    deals_without_next_action: int


def _rate(numerator: int, denominator: int) -> Rate:
    return Rate(
        numerator=numerator,
        denominator=denominator,
        rate=round(numerator / denominator, 4) if denominator else None,
    )


@router.get("/summary")
def summary(f: FiltersDep) -> Summary:
    db = f.db
    won_in_period = and_(
        Deal.status == DealStatus.WON,
        Deal.archived_at.is_(None),
        Deal.contract_date >= f.date_from,
        Deal.contract_date <= f.date_to,
        f.owner(Deal.closed_owner_id),
        f.customer_source(),
    )
    sales_count, sales_amount = db.execute(
        select(func.count(Deal.id), func.coalesce(func.sum(Deal.contract_amount), 0)).where(
            won_in_period
        )
    ).one()

    received = db.scalar(
        select(func.coalesce(func.sum(SIGNED_PAYMENT), 0))
        .join(Deal, Deal.id == Payment.deal_id)
        .where(
            Payment.voided_at.is_(None),
            Payment.paid_on >= f.date_from,
            Payment.paid_on <= f.date_to,
            f.owner(Deal.owner_id),
            f.customer_source(),
        )
    )

    paid_per_deal = (
        select(Payment.deal_id, func.sum(SIGNED_PAYMENT).label("paid"))
        .where(Payment.voided_at.is_(None))
        .group_by(Payment.deal_id)
        .subquery()
    )
    unpaid = db.scalar(
        select(
            func.coalesce(
                func.sum(
                    func.greatest(Deal.contract_amount - func.coalesce(paid_per_deal.c.paid, 0), 0)
                ),
                0,
            )
        )
        .select_from(Deal)
        .outerjoin(paid_per_deal, paid_per_deal.c.deal_id == Deal.id)
        .where(
            Deal.status == DealStatus.WON,
            Deal.archived_at.is_(None),
            f.owner(Deal.owner_id),
            f.customer_source(),
        )
    )

    open_deals = and_(
        Deal.status == DealStatus.OPEN,
        Deal.archived_at.is_(None),
        f.owner(Deal.owner_id),
        f.customer_source(),
    )
    pipeline_count, pipeline_amount = db.execute(
        select(func.count(Deal.id), func.coalesce(func.sum(Deal.amount), 0)).where(open_deals)
    ).one()
    without_next = db.scalar(
        select(func.count(Deal.id)).where(
            open_deals,
            ~exists().where(Activity.deal_id == Deal.id, Activity.status.in_(OPEN_STATUSES)),
        )
    )

    lead_filter = and_(
        Lead.archived_at.is_(None),
        Lead.created_at >= f.start,
        Lead.created_at < f.end,
        f.owner(Lead.owner_id),
        true() if f.source_id is None else Lead.source_id == f.source_id,
    )
    new_leads = db.scalar(select(func.count(Lead.id)).where(lead_filter)) or 0

    new_customers = db.scalar(
        select(func.count(Customer.id)).where(
            Customer.archived_at.is_(None),
            Customer.created_at >= f.start,
            Customer.created_at < f.end,
            f.owner(Customer.owner_id),
            true() if f.source_id is None else Customer.source_id == f.source_id,
        )
    )

    first_won = (
        select(Deal.customer_id, func.min(Deal.contract_date).label("first_date"))
        .where(Deal.status == DealStatus.WON, Deal.archived_at.is_(None))
        .group_by(Deal.customer_id)
        .subquery()
    )
    first_purchase = db.scalar(
        select(func.count())
        .select_from(first_won)
        .join(Customer, Customer.id == first_won.c.customer_id)
        .where(
            first_won.c.first_date >= f.date_from,
            first_won.c.first_date <= f.date_to,
            f.owner(Customer.owner_id),
            true() if f.source_id is None else Customer.source_id == f.source_id,
        )
    )

    win_lose = dict(
        db.execute(
            select(Deal.status, func.count(Deal.id))
            .where(
                Deal.status.in_([DealStatus.WON, DealStatus.LOST]),
                Deal.archived_at.is_(None),
                Deal.closed_at >= f.start,
                Deal.closed_at < f.end,
                f.owner(Deal.closed_owner_id),
                f.customer_source(),
            )
            .group_by(Deal.status)
        ).all()
    )
    won, lost = win_lose.get(DealStatus.WON, 0), win_lose.get(DealStatus.LOST, 0)

    converted = db.scalar(
        select(func.count(Lead.id)).where(
            lead_filter,
            exists().where(
                Deal.customer_id == Lead.converted_customer_id,
                Deal.status == DealStatus.WON,
                Deal.contract_date <= f.evaluated_on,
            ),
        )
    )

    first_contacts = db.execute(
        select(Lead.created_at, func.min(Activity.completed_at))
        .join(Activity, Activity.lead_id == Lead.id)
        .where(
            lead_filter,
            Activity.status == ActivityStatus.DONE,
            Activity.type.in_([ActivityType.CALL, ActivityType.MEETING]),
        )
        .group_by(Lead.id, Lead.created_at)
    ).all()
    hours = [(done - created).total_seconds() / 3600 for created, done in first_contacts if done]

    overdue = db.scalar(
        select(func.count(Activity.id)).where(
            Activity.status.in_(OPEN_STATUSES),
            Activity.due_date < today(),
            f.owner(Activity.owner_id),
        )
    )

    return Summary(
        currency=CURRENCY,
        date_from=f.date_from,
        date_to=f.date_to,
        evaluated_on=f.evaluated_on,
        sales=Money(count=sales_count, amount=int(sales_amount or 0)),
        received=int(received or 0),
        unpaid_balance=int(unpaid or 0),
        pipeline=Money(count=pipeline_count, amount=int(pipeline_amount or 0)),
        new_leads=new_leads,
        new_customers=new_customers or 0,
        first_purchase_customers=first_purchase or 0,
        win_rate=_rate(won, won + lost),
        lead_conversion=_rate(converted or 0, new_leads),
        first_contact_median_hours=round(statistics.median(hours), 1) if hours else None,
        overdue_activities=overdue or 0,
        deals_without_next_action=without_next or 0,
    )


# -- daily series (grouped into Jalali months by the client) ------------------


class Point(BaseModel):
    date: date
    value: int


Metric = Literal["sales_amount", "sales_count", "received", "new_leads", "new_customers"]


@router.get("/series")
def series(f: FiltersDep, metric: Metric) -> list[Point]:
    """Daily values; the web app groups them into Jalali weeks or months."""
    if metric in ("sales_amount", "sales_count"):
        value = func.sum(Deal.contract_amount) if metric == "sales_amount" else func.count(Deal.id)
        query = (
            select(Deal.contract_date, value)
            .where(
                Deal.status == DealStatus.WON,
                Deal.archived_at.is_(None),
                Deal.contract_date >= f.date_from,
                Deal.contract_date <= f.date_to,
                f.owner(Deal.closed_owner_id),
                f.customer_source(),
            )
            .group_by(Deal.contract_date)
        )
    elif metric == "received":
        query = (
            select(Payment.paid_on, func.sum(SIGNED_PAYMENT))
            .join(Deal, Deal.id == Payment.deal_id)
            .where(
                Payment.voided_at.is_(None),
                Payment.paid_on >= f.date_from,
                Payment.paid_on <= f.date_to,
                f.owner(Deal.owner_id),
                f.customer_source(),
            )
            .group_by(Payment.paid_on)
        )
    else:
        model = Lead if metric == "new_leads" else Customer
        day = local_date(model.created_at)
        query = (
            select(day, func.count(model.id))
            .where(
                model.archived_at.is_(None),
                model.created_at >= f.start,
                model.created_at < f.end,
                f.owner(model.owner_id),
                true() if f.source_id is None else model.source_id == f.source_id,
            )
            .group_by(day)
        )
    return [
        Point(date=d, value=int(v or 0))
        for d, v in f.db.execute(query.order_by(literal_column("1")))
    ]


# -- inbound deals ------------------------------------------------------------


class InboundRow(BaseModel):
    key: str
    label: str
    open: int
    won: int
    lost: int


class Inbound(BaseModel):
    currency: str
    measure: Literal["count", "amount"]
    evaluated_on: date
    rows: list[InboundRow]


@router.get("/inbound-deals")
def inbound_deals(
    f: FiltersDep,
    group: Literal["time", "user", "source"] = "time",
    measure: Literal["count", "amount"] = "count",
) -> Inbound:
    """Deals created in the period, split by today's status (spec 4.4, image 14/16).
    Amount uses the contract amount for won deals and the estimate otherwise."""
    value = (
        case(
            (Deal.status == DealStatus.WON, Deal.contract_amount),
            else_=func.coalesce(Deal.amount, 0),
        )
        if measure == "amount"
        else 1
    )

    def by_status(s: DealStatus) -> ColumnElement[int]:
        return func.coalesce(func.sum(case((Deal.status == s, value), else_=0)), 0)

    if group == "time":
        key: ColumnElement[Any] | InstrumentedAttribute[Any] = local_date(Deal.created_at)
    elif group == "user":
        key = Deal.created_owner_id
    else:
        key = Customer.source_id

    query = (
        select(
            key, by_status(DealStatus.OPEN), by_status(DealStatus.WON), by_status(DealStatus.LOST)
        )
        .select_from(Deal)
        .join(Customer, Customer.id == Deal.customer_id)
        .where(
            Deal.archived_at.is_(None),
            Deal.created_at >= f.start,
            Deal.created_at < f.end,
            f.owner(Deal.created_owner_id),
            f.customer_source(),
        )
        .group_by(key)
    )
    raw = f.db.execute(query).all()
    labels: dict[object, str] = {}
    if group == "user":
        labels = {
            u.id: u.full_name
            for u in f.db.scalars(select(User).where(User.id.in_([r[0] for r in raw])))
        }
    elif group == "source":
        labels = {s.id: s.name for s in f.db.scalars(select(LeadSource))}
    rows = [
        InboundRow(
            key=str(k) if k is not None else "none",
            label=k.isoformat() if isinstance(k, date) else labels.get(k, "نامشخص"),
            open=int(o),
            won=int(w),
            lost=int(lo),
        )
        for k, o, w, lo in raw
    ]
    rows.sort(key=lambda r: r.key if group == "time" else -(r.open + r.won + r.lost))
    return Inbound(currency=CURRENCY, measure=measure, evaluated_on=f.evaluated_on, rows=rows)


# -- by source, lost reasons, pipeline -----------------------------------------


class SourceRow(BaseModel):
    source: str
    won_count: int
    won_amount: int


@router.get("/sales-by-source")
def sales_by_source(f: FiltersDep) -> list[SourceRow]:
    rows = f.db.execute(
        select(
            LeadSource.name, func.count(Deal.id), func.coalesce(func.sum(Deal.contract_amount), 0)
        )
        .select_from(Deal)
        .join(Customer, Customer.id == Deal.customer_id)
        .outerjoin(LeadSource, LeadSource.id == Customer.source_id)
        .where(
            Deal.status == DealStatus.WON,
            Deal.archived_at.is_(None),
            Deal.contract_date >= f.date_from,
            Deal.contract_date <= f.date_to,
            f.owner(Deal.closed_owner_id),
            f.customer_source(),
        )
        .group_by(LeadSource.name)
        .order_by(func.sum(Deal.contract_amount).desc())
    ).all()
    return [
        SourceRow(source=name or "نامشخص", won_count=c, won_amount=int(a or 0))
        for name, c, a in rows
    ]


class ReasonRow(BaseModel):
    reason: str
    count: int


@router.get("/lost-reasons")
def lost_reasons(f: FiltersDep) -> list[ReasonRow]:
    rows = f.db.execute(
        select(Deal.lost_reason, func.count(Deal.id))
        .where(
            Deal.status == DealStatus.LOST,
            Deal.archived_at.is_(None),
            Deal.closed_at >= f.start,
            Deal.closed_at < f.end,
            f.owner(Deal.closed_owner_id),
            f.customer_source(),
        )
        .group_by(Deal.lost_reason)
        .order_by(func.count(Deal.id).desc())
        .limit(20)
    ).all()
    return [ReasonRow(reason=r or "—", count=c) for r, c in rows]


class StageRow(BaseModel):
    stage_id: uuid.UUID
    stage: str
    count: int
    amount: int


@router.get("/pipeline")
def pipeline(db: DbDep, scope: ScopeDep, owner_id: uuid.UUID | None = None) -> list[StageRow]:
    """Open deals per active stage, now (the overview's stage distribution)."""
    owners = _owners(db, scope, owner_id, None)
    counts = {
        sid: (int(c), int(a or 0))
        for sid, c, a in db.execute(
            select(Deal.stage_id, func.count(Deal.id), func.coalesce(func.sum(Deal.amount), 0))
            .where(
                Deal.status == DealStatus.OPEN,
                Deal.archived_at.is_(None),
                true() if owners is None else Deal.owner_id.in_(owners),
            )
            .group_by(Deal.stage_id)
        )
    }
    stages = db.scalars(select(Stage).where(Stage.is_active.is_(True)).order_by(Stage.sort_order))
    return [
        StageRow(
            stage_id=s.id,
            stage=s.name,
            count=counts.get(s.id, (0, 0))[0],
            amount=counts.get(s.id, (0, 0))[1],
        )
        for s in stages
    ]


# -- needs follow-up -------------------------------------------------------------


class FollowUpRow(BaseModel):
    deal_id: uuid.UUID
    title: str
    customer: str
    # The company the deal is with, when there is one (shown instead of the person).
    organization: str | None = None
    owner: UserRef
    reason: Literal["no_next_action", "overdue"]
    next_activity: ActivityBrief | None


@router.get("/needs-follow-up")
def needs_follow_up(
    db: DbDep,
    scope: ScopeDep,
    owner_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[FollowUpRow]:
    """Open deals with no planned next action, or whose next action is overdue (spec 4.2)."""
    owners = _owners(db, scope, owner_id, None)
    deals = list(
        db.scalars(
            select(Deal)
            .where(
                Deal.status == DealStatus.OPEN,
                Deal.archived_at.is_(None),
                true() if owners is None else Deal.owner_id.in_(owners),
            )
            .order_by(Deal.updated_at)
        ).unique()
    )
    upcoming = next_activities(db, [d.id for d in deals])
    rows: list[FollowUpRow] = []
    for d in deals:
        nxt = upcoming.get(d.id)
        if nxt is None or nxt.overdue:
            rows.append(
                FollowUpRow(
                    deal_id=d.id,
                    title=d.title,
                    customer=d.customer.full_name,
                    organization=d.organization.name if d.organization else None,
                    owner=UserRef.model_validate(d.owner),
                    reason="no_next_action" if nxt is None else "overdue",
                    next_activity=nxt,
                )
            )
    return rows[:limit]


# -- team performance -----------------------------------------------------------


class PerformanceRow(BaseModel):
    user: UserRef
    inbound_deals: int
    won_count: int
    won_amount: int
    lost_count: int
    win_rate: float | None
    open_pipeline: int
    activities_done: int
    overdue_activities: int


@router.get("/team")
def team_performance(f: FiltersDep) -> list[PerformanceRow]:
    """Per person: closed sales by owner at closing, inbound by owner at creation,
    pipeline and overdue work by current owner (spec 4.4)."""
    db = f.db
    users = list(
        db.scalars(
            select(User).where(User.is_active.is_(True), f.owner(User.id)).order_by(User.full_name)
        )
    )

    def grouped(query: object) -> dict[uuid.UUID, tuple[int, ...]]:
        return {row[0]: tuple(int(x or 0) for x in row[1:]) for row in db.execute(query)}  # type: ignore[call-overload]

    won = grouped(
        select(Deal.closed_owner_id, func.count(Deal.id), func.sum(Deal.contract_amount))
        .where(
            Deal.status == DealStatus.WON,
            Deal.archived_at.is_(None),
            Deal.contract_date >= f.date_from,
            Deal.contract_date <= f.date_to,
            f.customer_source(),
        )
        .group_by(Deal.closed_owner_id)
    )
    lost = grouped(
        select(Deal.closed_owner_id, func.count(Deal.id))
        .where(
            Deal.status == DealStatus.LOST,
            Deal.archived_at.is_(None),
            Deal.closed_at >= f.start,
            Deal.closed_at < f.end,
            f.customer_source(),
        )
        .group_by(Deal.closed_owner_id)
    )
    closed_won = grouped(
        select(Deal.closed_owner_id, func.count(Deal.id))
        .where(
            Deal.status == DealStatus.WON,
            Deal.archived_at.is_(None),
            Deal.closed_at >= f.start,
            Deal.closed_at < f.end,
            f.customer_source(),
        )
        .group_by(Deal.closed_owner_id)
    )
    inbound = grouped(
        select(Deal.created_owner_id, func.count(Deal.id))
        .where(
            Deal.archived_at.is_(None),
            Deal.created_at >= f.start,
            Deal.created_at < f.end,
            f.customer_source(),
        )
        .group_by(Deal.created_owner_id)
    )
    pipeline_now = grouped(
        select(Deal.owner_id, func.sum(Deal.amount))
        .where(Deal.status == DealStatus.OPEN, Deal.archived_at.is_(None), f.customer_source())
        .group_by(Deal.owner_id)
    )
    done = grouped(
        select(Activity.owner_id, func.count(Activity.id))
        .where(
            Activity.status == ActivityStatus.DONE,
            Activity.completed_at >= f.start,
            Activity.completed_at < f.end,
        )
        .group_by(Activity.owner_id)
    )
    overdue = grouped(
        select(Activity.owner_id, func.count(Activity.id))
        .where(Activity.status.in_(OPEN_STATUSES), Activity.due_date < today())
        .group_by(Activity.owner_id)
    )

    rows = []
    for u in users:
        cw, lo = closed_won.get(u.id, (0,))[0], lost.get(u.id, (0,))[0]
        rows.append(
            PerformanceRow(
                user=UserRef.model_validate(u),
                inbound_deals=inbound.get(u.id, (0,))[0],
                won_count=won.get(u.id, (0, 0))[0],
                won_amount=won.get(u.id, (0, 0))[1],
                lost_count=lo,
                win_rate=round(cw / (cw + lo), 4) if cw + lo else None,
                open_pipeline=pipeline_now.get(u.id, (0,))[0],
                activities_done=done.get(u.id, (0,))[0],
                overdue_activities=overdue.get(u.id, (0,))[0],
            )
        )
    return rows
