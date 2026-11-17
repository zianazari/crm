from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
