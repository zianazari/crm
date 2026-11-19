"""The demo data command (development and staging only)."""

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.dev import demo
from app.modules.activities.models import Activity
from app.modules.crm.models import Organization
from app.modules.identity.models import User, UserAvatar
from app.modules.sales.models import Deal, DealStatus
from tests.conftest import Org


def test_seed_builds_the_design_data_and_refuses_twice(org: Org) -> None:
    demo.seed()
    with SessionLocal() as db:
        names = set(db.scalars(select(Organization.name)))
        assert {"شرکت آبان", "گروه سپهر", "فروشگاه نارون", "شرکت آریا"} <= names
        open_deals = db.scalar(
            select(func.count()).select_from(Deal).where(Deal.status == DealStatus.OPEN)
        )
        assert open_deals == 24
        won_months = {
            d.contract_date.replace(day=1)
            for d in db.scalars(select(Deal).where(Deal.status == DealStatus.WON))
            if d.contract_date
        }
        assert len(won_months) >= 5  # a trend, not a single month
        assert (db.scalar(select(func.count()).select_from(Activity)) or 0) > 40
        staff = db.scalar(select(User).where(User.full_name == "علی رضایی"))
        assert staff is not None and staff.avatar_version
        photo = db.get(UserAvatar, staff.id)
        assert photo is not None and photo.content.startswith(b"\x89PNG")
    with pytest.raises(SystemExit):
        demo.seed()
    demo.seed(reset=True)  # recreates instead of doubling
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Organization)) == len(demo.ORGANIZATIONS)


def test_seed_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "environment", "production")
    with pytest.raises(SystemExit):
        demo.seed()
