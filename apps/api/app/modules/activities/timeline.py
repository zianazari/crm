"""Notes and the per-record timeline (spec 4.1 "unified file", 4.3 "deal file").

A deal's timeline holds only that deal's records. A customer's timeline holds the
customer's own records plus those of the customer's deals the user may see in full;
other people's deals never leak into it.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import ColumnElement, and_, or_, select, true
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.activities.models import Activity, ActivityStatus, Note
from app.modules.activities.schemas import (
    LinkRef,
    NoteIn,
    NoteOut,
    TimelineEntry,
    TimelineKind,
    TimelinePage,
)
from app.modules.activities.service import out, resolve_links, today, touch_records
from app.modules.auth.deps import DbDep, require_csrf
from app.modules.campaigns.models import DirectMessage
from app.modules.crm.access import AccessScope
from app.modules.crm.common import NOT_FOUND, ScopeDep, require_sales_access, unprocessable
from app.modules.crm.models import Customer, Lead
from app.modules.crm.schemas import UserRef
from app.modules.messaging.models import Channel
from app.modules.sales.models import Deal, DealHistory, DealStatus, Payment, PaymentKind

router = APIRouter(
    tags=["timeline"], dependencies=[Depends(require_csrf), Depends(require_sales_access)]
)

STATUS_TITLES = {DealStatus.WON: "فروش انجام شد", DealStatus.LOST: "به نتیجه نرسید"}


@router.post("/notes", status_code=status.HTTP_201_CREATED)
def create_note(body: NoteIn, db: DbDep, scope: ScopeDep) -> NoteOut:
    if not (body.lead_id or body.customer_id or body.deal_id):
        raise unprocessable("یادداشت باید به یک پرونده متصل باشد.")
    lead, customer, deal = resolve_links(db, scope, body.lead_id, body.customer_id, body.deal_id)
    note = Note(
        body=body.body.strip(),
        author_id=scope.user.id,
        author=scope.user,
        lead_id=lead.id if lead else None,
        customer_id=customer.id if customer else None,
        deal_id=deal.id if deal else None,
    )
    db.add(note)
    touch_records(datetime.now(UTC), deal, customer, lead, contact=False)
    db.commit()
    return NoteOut.model_validate(note)


@router.get("/timeline")
def timeline(
    db: DbDep,
    scope: ScopeDep,
    deal_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    kinds: Annotated[list[TimelineKind] | None, Query()] = None,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> TimelinePage:
    """Done and cancelled activities, notes, stage changes and payments, newest first.
    Page with ``before`` = the ``at`` of the last entry received."""
    if sum(x is not None for x in (deal_id, customer_id, lead_id)) != 1:
        raise unprocessable("دقیقاً یکی از فروش، مشتری یا مشتری احتمالی را مشخص کنید.")
    wanted = set(kinds or ["activity", "note", "stage", "payment", "message"])
    deal_ids, activity_scope, note_scope = _subject(db, scope, deal_id, customer_id, lead_id)

    entries: list[TimelineEntry] = []
    take = limit + 1
    if "activity" in wanted:
        query = select(Activity).where(
            activity_scope(Activity),
            or_(
                Activity.status == ActivityStatus.DONE,
                Activity.status == ActivityStatus.CANCELED,
            ),
        )
        # Done/cancelled activities are not edited afterwards, so their last change is
        # the moment they were completed or cancelled.
        rows = db.scalars(
            query.where(_before(Activity.updated_at, before))
            .order_by(Activity.updated_at.desc())
            .limit(take)
        )
        on = today()
        for a in rows:
            entries.append(
                TimelineEntry(
                    kind="activity",
                    id=a.id,
                    at=a.updated_at,
                    actor=UserRef.model_validate(a.completed_by or a.owner),
                    title=a.title,
                    body=a.outcome if a.status is ActivityStatus.DONE else a.cancel_reason,
                    activity=out(a, on),
                    deal=LinkRef(id=a.deal.id, name=a.deal.title)
                    if a.deal and not deal_id
                    else None,
                )
            )
    if "note" in wanted:
        for n in db.scalars(
            select(Note)
            .where(note_scope(Note), _before(Note.created_at, before))
            .order_by(Note.created_at.desc())
            .limit(take)
        ):
            entries.append(
                TimelineEntry(
                    kind="note",
                    id=n.id,
                    at=n.created_at,
                    actor=UserRef.model_validate(n.author),
                    title="یادداشت",
                    body=n.body,
                )
            )
    if "message" in wanted:
        for m in db.scalars(
            select(DirectMessage)
            .where(note_scope(DirectMessage), _before(DirectMessage.created_at, before))
            .order_by(DirectMessage.created_at.desc())
            .limit(take)
        ):
            label = "پیامک" if m.channel is Channel.SMS else "ایمیل"
            entries.append(
                TimelineEntry(
                    kind="message",
                    id=m.id,
                    at=m.created_at,
                    actor=UserRef.model_validate(m.sender),
                    title=f"{label} «{m.template_name}» به {m.contact_name}",
                    body=m.text,
                    message_status=m.message.status.value if m.message else None,
                    deal=_deal_ref(db, m.deal_id) if m.deal_id and not deal_id else None,
                )
            )
    if "stage" in wanted and deal_ids:
        for h in db.scalars(
            select(DealHistory)
            .where(DealHistory.deal_id.in_(deal_ids), _before(DealHistory.changed_at, before))
            .order_by(DealHistory.changed_at.desc())
            .limit(take)
        ):
            entries.append(
                TimelineEntry(
                    kind="stage",
                    id=h.id,
                    at=h.changed_at,
                    actor=UserRef.model_validate(h.changed_by),
                    title=_stage_title(h),
                    body=h.reason,
                    deal=_deal_ref(db, h.deal_id) if not deal_id else None,
                )
            )
    if "payment" in wanted and deal_ids:
        for p in db.scalars(
            select(Payment)
            .where(Payment.deal_id.in_(deal_ids), _before(Payment.created_at, before))
            .order_by(Payment.created_at.desc())
            .limit(take)
        ):
            label = "بازپرداخت" if p.kind is PaymentKind.REFUND else "پرداخت"
            entries.append(
                TimelineEntry(
                    kind="payment",
                    id=p.id,
                    at=p.created_at,
                    actor=UserRef.model_validate(p.recorded_by),
                    title=f"{label} {p.amount:,} تومان" + (" (باطل‌شده)" if p.voided_at else ""),
                    body=p.note,
                    deal=_deal_ref(db, p.deal_id) if not deal_id else None,
                )
            )

    entries.sort(key=lambda e: e.at, reverse=True)
    return TimelinePage(items=entries[:limit], has_more=len(entries) > limit)


def _before(
    column: InstrumentedAttribute[datetime], before: datetime | None
) -> ColumnElement[bool]:
    return column < before if before is not None else true()


Subject = type[Activity] | type[Note] | type[DirectMessage]
Belongs = Callable[[Subject], ColumnElement[bool]]


def _subject(
    db: Session,
    scope: AccessScope,
    deal_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    lead_id: uuid.UUID | None,
) -> tuple[list[uuid.UUID], Belongs, Belongs]:
    """Returns the deal ids whose history belongs on this timeline, and filters selecting
    the activities and notes that do."""
    if deal_id is not None:
        deal = db.get(Deal, deal_id)
        if deal is None:
            raise NOT_FOUND
        scope.require_full(deal.owner_id)

        def of_deal(model: Subject) -> ColumnElement[bool]:
            return model.deal_id == deal.id

        return [deal.id], of_deal, of_deal

    if lead_id is not None:
        lead = db.get(Lead, lead_id)
        if lead is None:
            raise NOT_FOUND
        scope.require_full(lead.owner_id)

        def of_lead(model: Subject) -> ColumnElement[bool]:
            return model.lead_id == lead.id

        return [], of_lead, of_lead

    customer = db.get(Customer, customer_id) if customer_id else None
    if customer is None:
        raise NOT_FOUND
    scope.require_full(customer.owner_id)
    visible_deals = [
        d.id
        for d in db.scalars(select(Deal).where(Deal.customer_id == customer.id)).unique()
        if scope.has_full_access(d.owner_id)
    ]

    def belongs(model: Subject) -> ColumnElement[bool]:
        # The customer's own items, or items of deals the user may see in full.
        return and_(
            model.customer_id == customer.id,
            or_(model.deal_id.is_(None), model.deal_id.in_(visible_deals)),
        )

    return visible_deals, belongs, belongs


def _deal_ref(db: Session, deal_id: uuid.UUID) -> LinkRef | None:
    deal = db.get(Deal, deal_id)
    return LinkRef(id=deal.id, name=deal.title) if deal else None


def _stage_title(h: DealHistory) -> str:
    if h.from_status is None:
        return f"فروش در مرحله «{h.to_stage.name}» ثبت شد"
    if h.from_status is DealStatus.OPEN and h.to_status is not DealStatus.OPEN:
        return f"نتیجه: {STATUS_TITLES[h.to_status]}"
    if h.from_status is not DealStatus.OPEN and h.to_status is DealStatus.OPEN:
        return f"بازگشایی در مرحله «{h.to_stage.name}»"
    from_name = h.from_stage.name if h.from_stage else "—"
    return f"انتقال از «{from_name}» به «{h.to_stage.name}»"
