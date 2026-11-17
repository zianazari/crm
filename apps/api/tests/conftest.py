"""Integration test setup: a dedicated ``crm_test`` database and Redis db 15.

Environment variables are set before the app is imported so cached settings,
the engine and the Redis client all point at the test resources, never at dev data.
"""

import os
from collections.abc import Iterator

from sqlalchemy.engine import make_url

_base_url = make_url(
    os.environ.get("CRM_DATABASE_URL", "postgresql+psycopg://crm:crm@localhost:5432/crm")
)
TEST_DATABASE_URL = _base_url.set(database="crm_test")
os.environ["CRM_ENVIRONMENT"] = "test"
os.environ["CRM_DATABASE_URL"] = TEST_DATABASE_URL.render_as_string(hide_password=False)
os.environ["CRM_REDIS_URL"] = os.environ.get("CRM_TEST_REDIS_URL", "redis://localhost:6379/15")
os.environ["CRM_COOKIE_SECURE"] = "false"  # TestClient talks plain http

import uuid  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth.sessions import SessionService  # noqa: E402
from app.modules.identity.models import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    admin = create_engine(_base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS crm_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE crm_test"))
    admin.dispose()
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    get_redis().flushdb()
    yield
    with SessionLocal() as db:
        db.execute(text("TRUNCATE auth_sessions, users, teams, tags CASCADE"))
        db.commit()
    get_redis().flushdb()


def login_as(user_id: uuid.UUID) -> TestClient:
    """A TestClient carrying a real session for the user (skips the OTP round trip)."""
    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user is not None
        tokens = SessionService(db, get_redis(), get_settings()).create(user, "pytest", None)
    client = TestClient(app)
    client.cookies.set("crm_access", tokens.access_token)
    client.cookies.set("crm_refresh", tokens.refresh_token)
    client.cookies.set("crm_csrf", tokens.csrf_token)
    client.headers["X-CSRF-Token"] = tokens.csrf_token
    return client
