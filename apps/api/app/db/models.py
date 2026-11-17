"""Imports every model module so ``Base.metadata`` is complete for Alembic."""

from app.db.base import Base
from app.modules.identity import models as identity_models

__all__ = ["Base", "identity_models"]
