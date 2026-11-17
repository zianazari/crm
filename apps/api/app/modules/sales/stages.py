"""Pipeline stage settings: managers and admins name, order and retire stages (spec 4.3)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.modules.auth.deps import DbDep, require_csrf
from app.modules.crm.access import AccessScope
from app.modules.crm.common import NOT_FOUND, ScopeDep, unprocessable
from app.modules.sales.deals import record_history
from app.modules.sales.models import Deal, DealStatus, Stage
from app.modules.sales.schemas import StageDeactivateIn, StageIn, StageOut

router = APIRouter(prefix="/stages", tags=["stages"], dependencies=[Depends(require_csrf)])


def _require_settings(scope: AccessScope) -> None:
    if not (scope.is_admin or scope.is_manager):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="فقط مدیر یا ادمین مراحل فروش را تنظیم می‌کند."
        )


@router.get("")
def list_stages(db: DbDep, _: ScopeDep, include_inactive: bool = False) -> list[StageOut]:
    query = select(Stage).order_by(Stage.sort_order, Stage.name)
    if not include_inactive:
        query = query.where(Stage.is_active.is_(True))
    return [StageOut.model_validate(s) for s in db.scalars(query)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_stage(body: StageIn, db: DbDep, scope: ScopeDep) -> StageOut:
    _require_settings(scope)
    stage = Stage(name=body.name.strip(), sort_order=body.sort_order)
    db.add(stage)
    db.commit()
    return StageOut.model_validate(stage)


@router.patch("/{stage_id}")
def update_stage(stage_id: uuid.UUID, body: StageIn, db: DbDep, scope: ScopeDep) -> StageOut:
    _require_settings(scope)
    stage = db.get(Stage, stage_id)
    if stage is None:
        raise NOT_FOUND
    stage.name = body.name.strip()
    stage.sort_order = body.sort_order
    db.commit()
    return StageOut.model_validate(stage)


@router.post("/{stage_id}/deactivate")
def deactivate_stage(
    stage_id: uuid.UUID, body: StageDeactivateIn, db: DbDep, scope: ScopeDep
) -> StageOut:
    """A stage with open deals can only be retired by moving those deals elsewhere."""
    _require_settings(scope)
    stage = db.get(Stage, stage_id)
    if stage is None:
        raise NOT_FOUND
    open_deals = list(
        db.scalars(
            select(Deal)
            .where(Deal.stage_id == stage.id, Deal.status == DealStatus.OPEN)
            .with_for_update(of=Deal)
        ).unique()
    )
    if open_deals:
        if body.move_to_stage_id is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"{len(open_deals)} فروش باز در این مرحله است؛ مرحله مقصد را انتخاب کنید.",
            )
        target = db.get(Stage, body.move_to_stage_id)
        if target is None or not target.is_active or target.id == stage.id:
            raise unprocessable("مرحله مقصد معتبر نیست.")
        for deal in open_deals:
            deal.stage_id, deal.stage = target.id, target
            deal.version += 1
            record_history(db, deal, scope, stage.id, DealStatus.OPEN, "غیرفعال‌شدن مرحله")
    remaining = db.scalar(
        select(func.count())
        .select_from(Stage)
        .where(Stage.is_active.is_(True), Stage.id != stage.id)
    )
    if not remaining:
        raise unprocessable("حداقل یک مرحله فعال لازم است.")
    stage.is_active = False
    db.commit()
    return StageOut.model_validate(stage)
