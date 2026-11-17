import enum
import logging
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger("crm.auth.otp")


class Channel(enum.StrEnum):
    SMS = "sms"
    EMAIL = "email"


class OtpSender(Protocol):
    def send(self, channel: Channel, destination: str, code: str) -> None: ...


class DevConsoleOtpSender:
    """Development only (spec section 0, decision 8): prints the code to the API log.

    Never used in test, staging or production, where raw codes must not be logged.
    """

    def send(self, channel: Channel, destination: str, code: str) -> None:
        logger.warning("DEV OTP via %s to %s: %s", channel.value, destination, code)


class SenderNotConfiguredError(RuntimeError):
    pass


def build_otp_sender(settings: Settings) -> OtpSender:
    if settings.is_development:
        return DevConsoleOtpSender()
    # The SMS/email providers are an open decision (spec section 13, item 8).
    raise SenderNotConfiguredError("No OTP delivery provider is configured")
