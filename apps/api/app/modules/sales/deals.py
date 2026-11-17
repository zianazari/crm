import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.auth.deps import DbDep, require_csrf
from app.modules.crm.access import AccessScope
from app.modules.crm.common import (
    NOT_FOUND,
    ScopeDep,
    archive,
    change_owner,
    day_bounds,
    paginate,
    resolve_owner,
    restore,
    unprocessable,
)
from app.modules.crm.models import Customer, Organization
from app.modules.crm.schemas import Page
from app.modules.sales.models import Deal, DealHistory, DealStatus, Payment, PaymentKind, Stage
from app.modules.sales.schemas import (
    AssignDealIn,
    Board,
    BoardColumn,
    BoardOutcome,
    DealCreate,
    DealLimited,
    DealOut,
    DealUpdate,
    DealView,
    HistoryOut,
    LoseIn,
    MoveIn,
    PaymentIn,
    PaymentOut,
    ReopenIn,
    StageOut,
    VoidIn,
    WinIn,
)

router = APIRouter(prefix="/deals", tags=["deals"], dependencies=[Depends(require_csrf)])

_CONFLICT: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"description": "Changed by someone else; body has the current deal"}
}
BOARD_COLUMN_LIMIT = 200


# -- loading & views -------------------------------------------------------


def payment_totals(db: Session, deal_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Net received per deal: payments minus refunds, ignoring voided entries."""
    if not deal_ids:
        return {}
    signed = case((Payment.kind == PaymentKind.REFUND, -Payment.amount), else_=Payment.amount)
    rows = db.execute(
        select(Payment.deal_id, func.coalesce(func.sum(signed), 0))
        .where(Payment.deal_id.in_(deal_ids), Payment.voided_at.is_(None))
        .group_by(Payment.deal_id)
    )
    return {deal_id: int(total) for deal_id, total in rows}


def full_view(deal: Deal, paid: int) -> DealOut:
    out = DealOut.model_validate(deal)
    out.paid_amount = paid
    if deal.status is DealStatus.WON and deal.contract_amount is not None:
        out.outstanding_amount = deal.contract_amount - paid
    return out


def views(db: Session, scope: AccessScope, deals: list[Deal]) -> list[DealOut | DealLimited]:
    full_ids = [d.id for d in deals if scope.has_full_access(d.owner_id)]
    totals = payment_totals(db, full_ids)
    return [
        full_view(d, totals.get(d.id, 0))
        if scope.has_full_access(d.owner_id)
        else DealLimited.model_validate(d)
        for d in deals
    ]


def view(db: Session, scope: AccessScope, deal: Deal) -> DealOut | DealLimited:
    return views(db, scope, [deal])[0]


def load(db: Session, deal_id: uuid.UUID, *, for_update: bool = False) -> Deal:
    query = select(Deal).where(Deal.id == deal_id)
    if for_update:
        query = query.with_for_update(of=Deal)
    deal = db.scalar(query)
    if deal is None:
        raise NOT_FOUND
    return deal


def load_for_change(db: Session, scope: AccessScope, deal_id: uuid.UUID, version: int) -> Deal:
    """Locks the deal, checks access, and rejects stale writes (spec 4.3: two users
    moving the same card must not silently overwrite each other)."""
    deal = load(db, deal_id, for_update=True)
    scope.require_full(deal.owner_id)
    if deal.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این فروش بایگانی شده است.")
    if deal.version != version:
        raise _StaleVersion(full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0)))
    return deal


class _StaleVersion(Exception):
    def __init__(self, current: DealOut) -> None:
        self.current = current


def stale_response(exc: _StaleVersion) -> JSONResponse:
    return JSONResponse(
        {
            "detail": "این فروش هم‌زمان توسط کاربر دیگری تغییر کرده است. وضعیت جدید نمایش داده شد.",
            "current": exc.current.model_dump(mode="json"),
        },
        status_code=status.HTTP_409_CONFLICT,
    )


def record_history(
    db: Session,
    deal: Deal,
    scope: AccessScope,
    from_stage_id: uuid.UUID | None,
    from_status: DealStatus | None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        DealHistory(
            deal_id=deal.id,
            from_stage_id=from_stage_id,
            to_stage_id=deal.stage_id,
            from_status=from_status,
            to_status=deal.status,
            owner_id=deal.owner_id,
            changed_by_id=scope.user.id,
            reason=reason,
            details=details,
        )
    )


def active_stage(db: Session, stage_id: uuid.UUID) -> Stage:
    stage = db.get(Stage, stage_id)
    if stage is None or not stage.is_active:
        raise unprocessable("مرحله انتخاب‌شده معتبر نیست.")
    return stage


def first_stage(db: Session) -> Stage:
    stage = db.scalar(
        select(Stage).where(Stage.is_active.is_(True)).order_by(Stage.sort_order, Stage.name)
    )
    if stage is None:
        raise unprocessable("هیچ مرحله فعالی برای مسیر فروش تعریف نشده است.")
    return stage


def check_organization(db: Session, customer: Customer, organization_id: uuid.UUID | None) -> None:
    if organization_id is None:
        return
    if all(link.organization_id != organization_id for link in customer.organizations):
        raise unprocessable("سازمان انتخاب‌شده به این مشتری متصل نیست.")
    organization = db.get(Organization, organization_id)
    if organization is None or organization.archived_at is not None:
        raise unprocessable("سازمان انتخاب‌شده معتبر نیست.")


def filtered(
    scope: AccessScope,
    q: str | None,
    owner_id: uuid.UUID | None,
    mine: bool,
    customer_id: uuid.UUID | None,
) -> Select[Deal]:
    query = select(Deal).join(Deal.customer).where(Deal.archived_at.is_(None))
    if q and q.strip():
        term = q.strip()
        query = query.where(
            or_(
                Deal.title.icontains(term, autoescape=True),
                Customer.full_name.icontains(term, autoescape=True),
            )
        )
    if owner_id:
        query = query.where(Deal.owner_id == owner_id)
    if mine:
        query = query.where(Deal.owner_id == scope.user.id)
    if customer_id:
        query = query.where(Deal.customer_id == customer_id)
    return query


# -- list, board, detail ---------------------------------------------------


@router.get("")
def list_deals(
    db: DbDep,
    scope: ScopeDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_: Annotated[DealStatus | None, Query(alias="status")] = None,
    stage_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    mine: bool = False,
    created_from: date | None = None,
    created_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[DealView]:
    query = filtered(scope, q, owner_id, mine, customer_id).order_by(
        Deal.created_at.desc(), Deal.id
    )
    if status_:
        query = query.where(Deal.status == status_)
    if stage_id:
        query = query.where(Deal.stage_id == stage_id)
    start, end = day_bounds(created_from, created_to)
    if start:
        query = query.where(Deal.created_at >= start)
    if end:
        query = query.where(Deal.created_at < end)
    rows, total = paginate(db, query, page, page_size)
    return Page[DealView](items=views(db, scope, rows), total=total, page=page, page_size=page_size)


@router.get("/board")
def board(
    db: DbDep,
    scope: ScopeDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    owner_id: uuid.UUID | None = None,
    mine: bool = False,
    closed_days: Annotated[int, Query(ge=1, le=3660)] = 30,
) -> Board:
    """Open deals per active stage, plus deals closed in the last ``closed_days`` days
    (organization time zone) in the final-result column. Column totals include only amounts the user
    can see, so they always equal the sum of the visible cards (acceptance criterion 19)."""
    base = filtered(scope, q, owner_id, mine, None)
    full = scope.full_access_filter(Deal.owner_id)
    stages = list(
        db.scalars(
            select(Stage).where(Stage.is_active.is_(True)).order_by(Stage.sort_order, Stage.name)
        )
    )

    open_deals = base.where(Deal.status == DealStatus.OPEN)
    stats = {
        stage_id: (int(count), int(total))
        for stage_id, count, total in db.execute(
            open_deals.with_only_columns(
                Deal.stage_id,
                func.count(Deal.id),
                func.coalesce(func.sum(case((full, Deal.amount), else_=0)), 0),
            ).group_by(Deal.stage_id)
        )
    }
    columns = []
    for stage in stages:
        rows = list(
            db.scalars(
                open_deals.where(Deal.stage_id == stage.id)
                .order_by(Deal.updated_at.desc(), Deal.id)
                .limit(BOARD_COLUMN_LIMIT)
            ).unique()
        )
        count, total = stats.get(stage.id, (0, 0))
        columns.append(
            BoardColumn(
                stage=StageOut.model_validate(stage),
                count=count,
                total_amount=total,
                deals=views(db, scope, rows),
                truncated=count > len(rows),
            )
        )

    today = datetime.now(ZoneInfo(get_settings().timezone)).date()
    since = today - timedelta(days=closed_days - 1)
    start, _ = day_bounds(since, None)
    closed = base.where(Deal.status != DealStatus.OPEN, Deal.closed_at >= start)
    outcome_stats = {
        s: (int(c), int(t))
        for s, c, t in db.execute(
            closed.with_only_columns(
                Deal.status,
                func.count(Deal.id),
                func.coalesce(func.sum(case((full, Deal.contract_amount), else_=0)), 0),
            ).group_by(Deal.status)
        )
    }
    closed_rows = list(
        db.scalars(
            closed.order_by(Deal.closed_at.desc(), Deal.id).limit(BOARD_COLUMN_LIMIT)
        ).unique()
    )
    won_count, won_total = outcome_stats.get(DealStatus.WON, (0, 0))
    lost_count, _ = outcome_stats.get(DealStatus.LOST, (0, 0))
    return Board(
        columns=columns,
        outcome=BoardOutcome(
            closed_from=since,
            won_count=won_count,
            won_total=won_total,
            lost_count=lost_count,
            deals=views(db, scope, closed_rows),
            truncated=won_count + lost_count > len(closed_rows),
        ),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_deal(body: DealCreate, db: DbDep, scope: ScopeDep) -> DealOut:
    customer = db.get(Customer, body.customer_id)
    if customer is None or customer.archived_at is not None:
        raise unprocessable("مشتری انتخاب‌شده معتبر نیست.")
    # A deal is opened on a customer file the user may work on.
    scope.require_full(customer.owner_id)
    check_organization(db, customer, body.organization_id)
    stage = active_stage(db, body.stage_id) if body.stage_id else first_stage(db)
    owner = resolve_owner(db, scope, body.owner_id)

    deal = Deal(
        title=body.title.strip(),
        description=body.description,
        customer=customer,
        organization_id=body.organization_id,
        owner=owner,
        owner_id=owner.id,
        created_owner_id=owner.id,
        created_by_id=scope.user.id,
        stage=stage,
        stage_id=stage.id,
        amount=body.amount,
        expected_close_date=body.expected_close_date,
    )
    db.add(deal)
    db.flush()
    record_history(db, deal, scope, None, None)
    db.commit()
    return full_view(deal, 0)


@router.get("/{deal_id}")
def get_deal(deal_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> DealView:
    deal = load(db, deal_id)
    if deal.archived_at is not None and not scope.can_manage(deal.owner_id):
        raise NOT_FOUND
    return view(db, scope, deal)


@router.patch("/{deal_id}", response_model=DealOut, responses=_CONFLICT)
def update_deal(
    deal_id: uuid.UUID, body: DealUpdate, db: DbDep, scope: ScopeDep
) -> DealOut | JSONResponse:
    try:
        deal = load_for_change(db, scope, deal_id, body.version)
    except _StaleVersion as exc:
        return stale_response(exc)
    data = body.model_dump(exclude_unset=True, exclude={"version"})
    if "organization_id" in data:
        check_organization(db, deal.customer, data["organization_id"])
    if data.get("title") is None:
        data.pop("title", None)
    for key, value in data.items():
        setattr(deal, key, value)
    deal.version += 1
    db.commit()
    return full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0))


@router.post("/{deal_id}/move", response_model=DealOut, responses=_CONFLICT)
def move_deal(
    deal_id: uuid.UUID, body: MoveIn, db: DbDep, scope: ScopeDep
) -> DealOut | JSONResponse:
    try:
        deal = load_for_change(db, scope, deal_id, body.version)
    except _StaleVersion as exc:
        return stale_response(exc)
    if deal.status is not DealStatus.OPEN:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="فروش بسته‌شده را باید ابتدا بازگشایی کرد."
        )
    stage = active_stage(db, body.stage_id)
    if stage.id != deal.stage_id:
        previous = deal.stage_id
        deal.stage_id, deal.stage = stage.id, stage
        deal.version += 1
        record_history(db, deal, scope, previous, DealStatus.OPEN)
        db.commit()
    return full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0))


def _close(
    db: Session, scope: AccessScope, deal: Deal, new_status: DealStatus, reason: str | None = None
) -> None:
    if deal.status is not DealStatus.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این فروش قبلاً بسته شده است.")
    deal.status = new_status
    deal.closed_at = datetime.now(UTC)
    deal.closed_by_id = scope.user.id
    deal.closed_owner_id = deal.owner_id
    deal.version += 1
    record_history(db, deal, scope, deal.stage_id, DealStatus.OPEN, reason)


@router.post("/{deal_id}/win", response_model=DealOut, responses=_CONFLICT)
def win_deal(deal_id: uuid.UUID, body: WinIn, db: DbDep, scope: ScopeDep) -> DealOut | JSONResponse:
    """Won = signed contract: amount and date are required (spec section 0, decision 2)."""
    try:
        deal = load_for_change(db, scope, deal_id, body.version)
    except _StaleVersion as exc:
        return stale_response(exc)
    deal.contract_amount = body.contract_amount
    deal.contract_date = body.contract_date
    _close(db, scope, deal, DealStatus.WON)
    db.commit()
    return full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0))


@router.post("/{deal_id}/lose", response_model=DealOut, responses=_CONFLICT)
def lose_deal(
    deal_id: uuid.UUID, body: LoseIn, db: DbDep, scope: ScopeDep
) -> DealOut | JSONResponse:
    try:
        deal = load_for_change(db, scope, deal_id, body.version)
    except _StaleVersion as exc:
        return stale_response(exc)
    deal.lost_reason = body.lost_reason.strip()
    _close(db, scope, deal, DealStatus.LOST, deal.lost_reason)
    db.commit()
    return full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0))


@router.post("/{deal_id}/reopen", response_model=DealOut, responses=_CONFLICT)
def reopen_deal(
    deal_id: uuid.UUID, body: ReopenIn, db: DbDep, scope: ScopeDep
) -> DealOut | JSONResponse:
    """Managers only, with a reason (spec 4.3). The cleared contract details are kept in
    the history entry so reports and audits can see what changed."""
    try:
        deal = load_for_change(db, scope, deal_id, body.version)
    except _StaleVersion as exc:
        return stale_response(exc)
    scope.require_manage(deal.owner_id)
    if deal.status is DealStatus.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این فروش باز است.")
    previous_status, previous_stage = deal.status, deal.stage_id
    details = {
        "contract_amount": deal.contract_amount,
        "contract_date": deal.contract_date.isoformat() if deal.contract_date else None,
        "lost_reason": deal.lost_reason,
        "closed_at": deal.closed_at.isoformat() if deal.closed_at else None,
    }
    if body.stage_id is not None:
        stage = active_stage(db, body.stage_id)
        deal.stage_id, deal.stage = stage.id, stage
    elif not deal.stage.is_active:
        stage = first_stage(db)
        deal.stage_id, deal.stage = stage.id, stage
    deal.status = DealStatus.OPEN
    deal.contract_amount = deal.contract_date = None
    deal.lost_reason = None
    deal.closed_at = None
    deal.closed_by_id = deal.closed_owner_id = None
    deal.version += 1
    record_history(db, deal, scope, previous_stage, previous_status, body.reason.strip(), details)
    db.commit()
    return full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0))


@router.post("/{deal_id}/assign")
def assign_deal(deal_id: uuid.UUID, body: AssignDealIn, db: DbDep, scope: ScopeDep) -> DealOut:
    deal = load(db, deal_id, for_update=True)
    change_owner(db, scope, deal, "deal", body.owner_id, body.reason)
    deal.version += 1
    db.commit()
    return full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0))


@router.post("/{deal_id}/archive")
def archive_deal(deal_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> DealOut:
    """Soft delete, distinct from closing; managers and admins only, after confirmation."""
    deal = load(db, deal_id, for_update=True)
    archive(scope, deal)
    deal.version += 1
    db.commit()
    return full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0))


@router.post("/{deal_id}/restore")
def restore_deal(deal_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> DealOut:
    deal = load(db, deal_id, for_update=True)
    restore(scope, deal)
    deal.version += 1
    db.commit()
    return full_view(deal, payment_totals(db, [deal.id]).get(deal.id, 0))


@router.get("/{deal_id}/history")
def deal_history(deal_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> list[HistoryOut]:
    deal = load(db, deal_id)
    scope.require_full(deal.owner_id)
    rows = db.scalars(
        select(DealHistory)
        .where(DealHistory.deal_id == deal.id)
        .order_by(DealHistory.changed_at.desc(), DealHistory.id)
    )
    return [HistoryOut.model_validate(r) for r in rows]


# -- payments --------------------------------------------------------------


@router.get("/{deal_id}/payments")
def list_payments(deal_id: uuid.UUID, db: DbDep, scope: ScopeDep) -> list[PaymentOut]:
    deal = load(db, deal_id)
    scope.require_full(deal.owner_id)
    rows = db.scalars(
        select(Payment)
        .where(Payment.deal_id == deal.id)
        .order_by(Payment.paid_on.desc(), Payment.created_at.desc())
    )
    return [PaymentOut.model_validate(p) for p in rows]


@router.post("/{deal_id}/payments", status_code=status.HTTP_201_CREATED)
def add_payment(deal_id: uuid.UUID, body: PaymentIn, db: DbDep, scope: ScopeDep) -> PaymentOut:
    # Lock the deal so concurrent refunds cannot exceed what was received.
    deal = load(db, deal_id, for_update=True)
    scope.require_full(deal.owner_id)
    if deal.archived_at is not None or deal.status is DealStatus.LOST:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="برای این فروش پرداخت ثبت نمی‌شود.")
    if body.kind is PaymentKind.REFUND:
        received = payment_totals(db, [deal.id]).get(deal.id, 0)
        if body.amount > received:
            raise unprocessable("مبلغ بازپرداخت بیشتر از مبلغ دریافت‌شده است.")
    payment = Payment(
        deal_id=deal.id,
        kind=body.kind,
        amount=body.amount,
        currency=deal.currency,
        paid_on=body.paid_on,
        reference=body.reference,
        note=body.note,
        recorded_by_id=scope.user.id,
        recorded_by=scope.user,
    )
    db.add(payment)
    db.commit()
    return PaymentOut.model_validate(payment)


@router.post("/{deal_id}/payments/{payment_id}/void")
def void_payment(
    deal_id: uuid.UUID, payment_id: uuid.UUID, body: VoidIn, db: DbDep, scope: ScopeDep
) -> PaymentOut:
    """Payments are never deleted; a wrong entry is voided by a manager with a reason."""
    deal = load(db, deal_id, for_update=True)
    scope.require_manage(deal.owner_id)
    payment = db.get(Payment, payment_id)
    if payment is None or payment.deal_id != deal.id:
        raise NOT_FOUND
    if payment.voided_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="این پرداخت قبلاً باطل شده است.")
    if payment.kind is PaymentKind.PAYMENT:
        remaining = payment_totals(db, [deal.id]).get(deal.id, 0) - payment.amount
        if remaining < 0:
            raise unprocessable("ابتدا بازپرداخت‌های مرتبط را باطل کنید.")
    payment.voided_at = datetime.now(UTC)
    payment.voided_by_id = scope.user.id
    payment.void_reason = body.reason.strip()
    db.commit()
    return PaymentOut.model_validate(payment)
