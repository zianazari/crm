"""Imports every model module so ``Base.metadata`` is complete for Alembic."""

from app.db.base import Base
from app.modules.activities import models as activities_models
from app.modules.audit import models as audit_models
from app.modules.auth import models as auth_models
from app.modules.automation import models as automation_models
from app.modules.booking import models as booking_models
from app.modules.campaigns import models as campaigns_models
from app.modules.crm import models as crm_models
from app.modules.identity import models as identity_models
from app.modules.messaging import models as messaging_models
from app.modules.notifications import models as notifications_models
from app.modules.portal import models as portal_models
from app.modules.sales import models as sales_models
from app.modules.tickets import models as tickets_models

__all__ = [
    "Base",
    "activities_models",
    "audit_models",
    "auth_models",
    "automation_models",
    "booking_models",
    "campaigns_models",
    "crm_models",
    "identity_models",
    "messaging_models",
    "notifications_models",
    "portal_models",
    "sales_models",
    "tickets_models",
]
