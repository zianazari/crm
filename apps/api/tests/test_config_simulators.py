"""The SMS simulator is refused outside development and test, except a demo staging."""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def make(environment: str, demo: bool = False) -> Settings:
    return Settings(
        environment=environment,
        demo_simulators=demo,
        jwt_secret=SecretStr("j" * 40),
        otp_secret=SecretStr("o" * 40),
    )


def test_simulator_only_in_demo_staging() -> None:
    assert make("staging", demo=True).sms_provider == "sink"
    with pytest.raises(ValidationError):
        make("staging")
    with pytest.raises(ValidationError):
        make("production", demo=True)
