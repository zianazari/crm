"""OTP challenges in Redis (spec section 8).

* Only an HMAC of the code (keyed with a server secret and bound to the challenge id)
  is stored; the raw code is never persisted.
* Verification, attempt counting and consumption run in one Lua script, so a code
  can be used once and the attempt limit cannot be raced.
* The response to a request never reveals whether an account exists.
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.normalize import normalize_email, normalize_mobile, normalize_otp_code
from app.modules.auth.sender import Channel, OtpContext, OtpSender
from app.modules.identity.models import User

logger = logging.getLogger("crm.auth.otp")

_HOUR = 3600

_VERIFY_SCRIPT = """
local key = KEYS[1]
if redis.call('EXISTS', key) == 0 then
  return ''
end
local attempts = redis.call('HINCRBY', key, 'attempts', 1)
if attempts > tonumber(ARGV[2]) then
  redis.call('DEL', key)
  return ''
end
if redis.call('HGET', key, 'code_hmac') == ARGV[1] then
  local user_id = redis.call('HGET', key, 'user_id')
  redis.call('DEL', key)
  return user_id
end
if attempts >= tonumber(ARGV[2]) then
  redis.call('DEL', key)
end
return ''
"""


class InvalidDestinationError(ValueError):
    pass


class RateLimitedError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"retry after {retry_after}s")
        self.retry_after = retry_after


@dataclass(frozen=True)
class OtpChallenge:
    challenge_id: str
    expires_in: int
    resend_after: int


def _challenge_key(challenge_id: str) -> str:
    return f"otp:challenge:{challenge_id}"


class OtpService:
    def __init__(self, redis: Redis, settings: Settings, sender: OtpSender) -> None:
        self.redis = redis
        self.settings = settings
        self.sender = sender

    # -- request -------------------------------------------------------------

    def request(self, db: Session, channel: Channel, raw_destination: str, ip: str) -> OtpChallenge:
        destination = (
            normalize_mobile(raw_destination)
            if channel is Channel.SMS
            else normalize_email(raw_destination)
        )
        if destination is None:
            raise InvalidDestinationError(channel.value)

        # These limits apply whether or not an account exists, so they reveal nothing.
        self._enforce_cooldown(f"otp:cooldown:{channel.value}:{destination}")
        self._enforce_limit(
            f"otp:rl:dest:{channel.value}:{destination}",
            self.settings.otp_max_requests_per_destination_hour,
        )
        self._enforce_limit(f"otp:rl:ip:{ip}", self.settings.otp_max_requests_per_ip_hour)

        challenge = OtpChallenge(
            challenge_id=secrets.token_urlsafe(24),
            expires_in=self.settings.otp_ttl_seconds,
            resend_after=self.settings.otp_resend_seconds,
        )

        column = User.mobile if channel is Channel.SMS else User.email
        user = db.scalar(select(User).where(column == destination, User.is_active.is_(True)))
        if user is None:
            return challenge

        # Per-account cap across channels: switching SMS/email does not reset it.
        # Exceeding it silently skips sending so the response stays identical.
        if not self._within_limit(
            f"otp:rl:account:{user.id}", self.settings.otp_max_requests_per_account_hour
        ):
            logger.info("OTP account limit reached for user %s", user.id)
            return challenge

        code = f"{secrets.randbelow(100_000):05d}"
        self._store(challenge.challenge_id, user.id, channel, destination, code)
        try:
            self.sender.send(
                channel,
                destination,
                code,
                OtpContext(challenge.challenge_id, user.id, self.settings.otp_ttl_seconds),
            )
        except Exception:
            # Keep the response identical; the failure is visible in logs and monitoring.
            logger.exception("OTP delivery failed for user %s", user.id)
            self.redis.delete(_challenge_key(challenge.challenge_id))
        return challenge

    def _store(
        self, challenge_id: str, user_id: uuid.UUID, channel: Channel, destination: str, code: str
    ) -> None:
        ttl = self.settings.otp_ttl_seconds
        active_key = f"otp:active:{user_id}"
        previous = self.redis.get(active_key)
        pipe = self.redis.pipeline(transaction=True)
        if previous:
            # A new code invalidates the previous one, even on another channel.
            pipe.delete(_challenge_key(str(previous)))
        pipe.hset(
            _challenge_key(challenge_id),
            mapping={
                "user_id": str(user_id),
                "channel": channel.value,
                "destination": destination,
                "purpose": "login",
                "code_hmac": self._code_hmac(challenge_id, code),
                "attempts": 0,
            },
        )
        pipe.expire(_challenge_key(challenge_id), ttl)
        pipe.set(active_key, challenge_id, ex=ttl)
        pipe.execute()

    # -- verify --------------------------------------------------------------

    def verify(self, challenge_id: str, raw_code: str, ip: str) -> uuid.UUID | None:
        """Returns the user id when the code is right; None for every kind of failure."""
        self._enforce_limit(f"otp:rl:verify:{ip}", self.settings.otp_max_verifications_per_ip_hour)
        code = normalize_otp_code(raw_code)
        result = self.redis.eval(
            _VERIFY_SCRIPT,
            1,
            _challenge_key(challenge_id),
            self._code_hmac(challenge_id, code),
            self.settings.otp_max_attempts,
        )
        if not result:
            return None
        self.redis.delete(f"otp:active:{result}")
        return uuid.UUID(str(result))

    # -- helpers -------------------------------------------------------------

    def _code_hmac(self, challenge_id: str, code: str) -> str:
        key = self.settings.otp_secret.get_secret_value().encode()
        return hmac.new(key, f"{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()

    def _enforce_cooldown(self, key: str) -> None:
        seconds = self.settings.otp_resend_seconds
        if not self.redis.set(key, 1, nx=True, ex=seconds):
            raise RateLimitedError(max(int(self.redis.ttl(key)), 1))

    def _within_limit(self, key: str, limit: int) -> bool:
        pipe = self.redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, _HOUR, nx=True)
        count, _ = pipe.execute()
        return int(count) <= limit

    def _enforce_limit(self, key: str, limit: int) -> None:
        if not self._within_limit(key, limit):
            raise RateLimitedError(max(int(self.redis.ttl(key)), 1))
