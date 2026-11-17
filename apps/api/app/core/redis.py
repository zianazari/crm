from functools import lru_cache

from redis import Redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> Redis:
    """Shared Redis client. Holds OTP challenges, rate-limit counters and live session ids.

    Any Redis error propagates; callers must fail closed (never skip a check).
    """
    return Redis.from_url(
        str(get_settings().redis_url),
        decode_responses=True,
        socket_timeout=2,
        socket_connect_timeout=2,
    )
