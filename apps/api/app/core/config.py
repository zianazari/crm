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
    # 127.0.0.1, not localhost: pika may try IPv6 ::1 first, where Compose does not listen.
    rabbitmq_url: str = "amqp://crm:crm@127.0.0.1:5672/"
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

    # Messaging (spec 7: outbox -> RabbitMQ -> worker -> provider adapter).
    # "console": development only, the OTP is printed to the API log (no queue needed).
    # "queue": messages go through the outbox, RabbitMQ and the worker.
    messaging_mode: Literal["console", "queue"] = "console"
    sms_provider: Literal["sink"] = "sink"  # real providers are added when chosen (spec 13.8)
    sms_sink_url: str = "http://localhost:8030"
    sms_webhook_secret: SecretStr = SecretStr("dev-only-sms-webhook-secret")
    # Where the SMS provider sends delivery reports (reachable from the provider).
    sms_callback_url: str | None = "http://host.docker.internal:8000/webhooks/sms"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    email_from: str = "CRM <no-reply@crm.local>"
    message_max_attempts: int = 5
    # Where the web app is reachable; used for links inside messages (unsubscribe).
    public_web_url: str = "http://localhost:3000"
    # Prefix for RabbitMQ exchange/queue names; tests use their own so a running dev
    # worker never consumes test messages.
    queue_namespace: str = ""
    provider_timeout_seconds: float = 10

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
        if self.environment in {"staging", "production"} and self.sms_provider == "sink":
            raise ValueError("The sms-sink simulator cannot be used outside development and test")
        for secret in (self.jwt_secret, self.otp_secret):
            if len(secret.get_secret_value()) < 32:
                raise ValueError("JWT and OTP secrets must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
