"""Provider adapters behind one small interface (spec 7: swappable SMS/email/LLM)."""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.core.config import Settings


class TemporaryError(Exception):
    """Nothing was sent (connection refused, 5xx before acceptance): safe to retry."""


class PermanentError(Exception):
    """The provider rejected the message (bad number, 4xx): retrying will not help."""


class AmbiguousError(Exception):
    """The request may have reached the provider but no answer came back. Re-sending
    could duplicate the message, so the status becomes "unknown" (spec 7)."""


@dataclass(frozen=True)
class Accepted:
    provider_message_id: str | None


class SmsProvider(Protocol):
    def send(self, to: str, text: str, idempotency_key: str) -> Accepted: ...


class EmailProvider(Protocol):
    def send(self, to: str, subject: str, text: str, idempotency_key: str) -> Accepted: ...


class SinkSmsProvider:
    """The local sms-sink simulator (development and tests only)."""

    def __init__(self, settings: Settings) -> None:
        self.url = settings.sms_sink_url.rstrip("/") + "/send"
        self.callback = settings.sms_callback_url
        self.timeout = settings.provider_timeout_seconds

    def send(self, to: str, text: str, idempotency_key: str) -> Accepted:
        try:
            response = httpx.post(
                self.url,
                json={
                    "to": to,
                    "text": text,
                    "idempotency_key": idempotency_key,
                    "callback_url": self.callback,
                },
                timeout=self.timeout,
            )
        except httpx.ConnectError as exc:
            raise TemporaryError(f"connect: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise AmbiguousError(f"timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise AmbiguousError(str(exc)) from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise TemporaryError(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise PermanentError(f"HTTP {response.status_code}: {response.text[:200]}")
        return Accepted(provider_message_id=str(response.json().get("message_id")))


class SmtpEmailProvider:
    """Plain SMTP: Mailpit in development, a real relay elsewhere."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, to: str, subject: str, text: str, idempotency_key: str) -> Accepted:
        s = self.settings
        message = EmailMessage()
        message["From"] = s.email_from
        message["To"] = to
        message["Subject"] = subject
        message["Message-ID"] = f"<{idempotency_key}@crm>"
        message.set_content(text)
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.provider_timeout_seconds) as smtp:
                if s.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if s.smtp_username and s.smtp_password:
                    smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
                smtp.send_message(message)
        except (
            ConnectionRefusedError,
            smtplib.SMTPConnectError,
            smtplib.SMTPServerDisconnected,
        ) as exc:
            raise TemporaryError(str(exc)) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise PermanentError(str(exc)) from exc
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise TemporaryError(str(exc)) from exc
            raise PermanentError(str(exc)) from exc
        except TimeoutError as exc:
            raise AmbiguousError(str(exc)) from exc
        return Accepted(provider_message_id=None)


@dataclass
class Providers:
    sms: SmsProvider
    email: EmailProvider


def build_providers(settings: Settings) -> Providers:
    return Providers(sms=SinkSmsProvider(settings), email=SmtpEmailProvider(settings))
