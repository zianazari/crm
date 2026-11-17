from functools import lru_cache
from typing import Literal, Self

from pydantic import PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder secrets that only work in development and test. Any other environment
# refuses to start with them (see ``_require_real_secrets``).
_DEV_JWT_SECRET = "dev-only-jwt-secret-change-me-0123456789abcdef"  # noqa: S105
_DEV_OTP_SECRET = "dev-only-otp-secret-change-me-0123456789abcdef"  # noqa: S105


class Settings(BaseSettings):
    """Application settings, read from environment variables (prefix ``CRM_``) or ``.env``.

    Defaults only match the local Docker Compose services. Staging and production
    must set every value explicitly; real secrets never live in the repository.
    """

    model_config = SettingsConfigDict(env_prefix="CRM_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: PostgresDsn = PostgresDsn("postgresql+psycopg://crm:crm@localhost:5432/crm")
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    rabbitmq_url: str = "amqp://crm:crm@localhost:5672/"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Organization defaults (spec section 0): base currency is toman, Jalali display.
    timezone: str = "Asia/Tehran"
    currency: str = "IRT"

    # Sessions (JWT access token + rotating opaque refresh token).
    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_issuer: str = "crm-api"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 14 * 24 * 60 * 60
    # Two tabs refreshing at once must not look like token theft.
    refresh_reuse_grace_seconds: int = 30
    cookie_secure: bool = True
    cookie_domain: str | None = None

    # OTP login (spec section 8). Values are the spec's proposed defaults.
    otp_secret: SecretStr = SecretStr(_DEV_OTP_SECRET)
    otp_ttl_seconds: int = 120
    otp_max_attempts: int = 5
    otp_resend_seconds: int = 60
    otp_max_requests_per_destination_hour: int = 5
    otp_max_requests_per_account_hour: int = 10
    otp_max_requests_per_ip_hour: int = 30
    otp_max_verifications_per_ip_hour: int = 60

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @model_validator(mode="after")
    def _require_real_secrets(self) -> Self:
        if self.environment in {"staging", "production"}:
            if self.jwt_secret.get_secret_value() == _DEV_JWT_SECRET:
                raise ValueError("CRM_JWT_SECRET must be set outside development")
            if self.otp_secret.get_secret_value() == _DEV_OTP_SECRET:
                raise ValueError("CRM_OTP_SECRET must be set outside development")
        for secret in (self.jwt_secret, self.otp_secret):
            if len(secret.get_secret_value()) < 32:
                raise ValueError("JWT and OTP secrets must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
