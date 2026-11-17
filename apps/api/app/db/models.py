"""Imports every model module so ``Base.metadata`` is complete for Alembic."""

from app.db.base import Base
from app.modules.auth import models as auth_models
from app.modules.crm import models as crm_models
from app.modules.identity import models as identity_models

__all__ = ["Base", "auth_models", "crm_models", "identity_models"]
