"""Session lifecycle: create, rotate refresh token, revoke.

The JWT alone cannot be revoked, so every authenticated request also checks that
``session:<sid>`` exists in Redis. Logout and user deactivation delete that key,
which ends access immediately (spec sections 5 and 8) instead of after token expiry.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis import Redis
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import AuthSession
from app.modules.auth.tokens import create_access_token
from app.modules.identity.models import User


class InvalidRefreshTokenError(Exception):
    pass


@dataclass(frozen=True)
class IssuedTokens:
    session_id: uuid.UUID
    user: User
    access_token: str
    refresh_token: str
    csrf_token: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _session_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}"


def is_session_live(redis: Redis, session_id: uuid.UUID) -> bool:
    return bool(redis.exists(_session_key(session_id)))


class SessionService:
    def __init__(self, db: Session, redis: Redis, settings: Settings) -> None:
        self.db = db
        self.redis = redis
        self.settings = settings

    def create(self, user: User, user_agent: str | None, ip: str | None) -> IssuedTokens:
        refresh_token = secrets.token_urlsafe(32)
        session = AuthSession(
            user_id=user.id,
            refresh_token_hash=_hash(refresh_token),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
            user_agent=(user_agent or "")[:300] or None,
            ip_address=ip,
        )
        self.db.add(session)
        self.db.commit()
        self._mark_live(session)
        return self._issue(session, user, refresh_token)

    def rotate(self, refresh_token: str) -> IssuedTokens:
        token_hash = _hash(refresh_token)
        now = datetime.now(UTC)
        session = self.db.scalar(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == token_hash)
            .with_for_update()
        )
        if session is None:
            self._handle_possible_reuse(token_hash, now)
            raise InvalidRefreshTokenError("unknown refresh token")

        user = self.db.get(User, session.user_id)
        if session.revoked_at is not None or session.expires_at <= now or user is None:
            raise InvalidRefreshTokenError("session ended")
        if not user.is_active:
            self.revoke(session.id, "user_inactive")
            raise InvalidRefreshTokenError("user inactive")

        new_refresh = secrets.token_urlsafe(32)
        session.previous_refresh_token_hash = session.refresh_token_hash
        session.refresh_token_hash = _hash(new_refresh)
        session.rotated_at = now
        self.db.commit()
        self._mark_live(session)
        return self._issue(session, user, new_refresh)

    def revoke(self, session_id: uuid.UUID, reason: str) -> None:
        self.db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
        )
        self.db.commit()
        self.redis.delete(_session_key(session_id))

    def revoke_by_refresh_token(self, refresh_token: str, reason: str) -> None:
        session_id = self.db.scalar(
            select(AuthSession.id).where(AuthSession.refresh_token_hash == _hash(refresh_token))
        )
        if session_id is not None:
            self.revoke(session_id, reason)

    def revoke_all_for_user(self, user_id: uuid.UUID, reason: str) -> None:
        """Used when a user is deactivated: every open session ends now."""
        session_ids = self.db.scalars(
            select(AuthSession.id).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
            )
        ).all()
        for session_id in session_ids:
            self.revoke(session_id, reason)

    def _handle_possible_reuse(self, token_hash: str, now: datetime) -> None:
        """An already-rotated refresh token came back. Outside a short grace window
        (two tabs refreshing together) this means the token leaked: end the session."""
        session = self.db.scalar(
            select(AuthSession).where(AuthSession.previous_refresh_token_hash == token_hash)
        )
        if session is None or session.revoked_at is not None:
            return
        grace = timedelta(seconds=self.settings.refresh_reuse_grace_seconds)
        if session.rotated_at is not None and now - session.rotated_at <= grace:
            return
        self.revoke(session.id, "refresh_token_reuse")

    def _mark_live(self, session: AuthSession) -> None:
        ttl = max(int((session.expires_at - datetime.now(UTC)).total_seconds()), 1)
        self.redis.set(_session_key(session.id), str(session.user_id), ex=ttl)

    def _issue(self, session: AuthSession, user: User, refresh_token: str) -> IssuedTokens:
        return IssuedTokens(
            session_id=session.id,
            user=user,
            access_token=create_access_token(self.settings, user.id, session.id, user.role),
            refresh_token=refresh_token,
            csrf_token=secrets.token_urlsafe(24),
        )
