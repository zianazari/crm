"""OTP login and JWT session behaviour (spec section 8, acceptance criterion 1)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import update

from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.modules.auth.deps import CSRF_COOKIE, CSRF_HEADER, get_otp_sender
from app.modules.auth.models import AuthSession
from app.modules.auth.sender import Channel
from app.modules.auth.sessions import SessionService
from app.modules.identity.models import Role, User

MOBILE = "+989121234567"
EMAIL = "sara@example.com"


class CapturingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[Channel, str, str]] = []

    def send(self, channel: Channel, destination: str, code: str) -> None:
        self.sent.append((channel, destination, code))

    @property
    def last_code(self) -> str:
        return self.sent[-1][2]


@pytest.fixture
def sender() -> Iterator[CapturingSender]:
    capturing = CapturingSender()
    app.dependency_overrides[get_otp_sender] = lambda: capturing
    yield capturing
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def user() -> User:
    with SessionLocal() as db:
        u = User(full_name="سارا احمدی", mobile=MOBILE, email=EMAIL, role=Role.SALES_REP)
        db.add(u)
        db.commit()
        return u


def request_code(client: TestClient, channel: str = "sms", destination: str = "09121234567") -> str:
    response = client.post(
        "/auth/otp/request", json={"channel": channel, "destination": destination}
    )
    assert response.status_code == 202, response.text
    return str(response.json()["challenge_id"])


def login(client: TestClient, sender: CapturingSender) -> None:
    challenge = request_code(client)
    response = client.post(
        "/auth/otp/verify", json={"challenge_id": challenge, "code": sender.last_code}
    )
    assert response.status_code == 200, response.text


def csrf(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}


# -- login ---------------------------------------------------------------


@pytest.mark.parametrize(("channel", "destination"), [("sms", "۰۹۱۲۱۲۳۴۵۶۷"), ("email", EMAIL)])
def test_login_by_sms_and_email(
    client: TestClient, sender: CapturingSender, user: User, channel: str, destination: str
) -> None:
    challenge = request_code(client, channel, destination)
    code = sender.last_code
    assert len(code) == 5 and code.isdigit()

    response = client.post("/auth/otp/verify", json={"challenge_id": challenge, "code": code})
    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert client.get("/auth/me").json()["full_name"] == "سارا احمدی"


def test_code_with_leading_zero_typed_in_persian_digits(
    client: TestClient, sender: CapturingSender, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.modules.auth.otp.secrets.randbelow", lambda _: 42)
    challenge = request_code(client)
    assert sender.last_code == "00042"
    response = client.post("/auth/otp/verify", json={"challenge_id": challenge, "code": "۰۰۰۴۲"})
    assert response.status_code == 200


def test_unknown_destination_gets_identical_response(
    client: TestClient, sender: CapturingSender, user: User
) -> None:
    known = client.post("/auth/otp/request", json={"channel": "sms", "destination": "09121234567"})
    unknown = client.post(
        "/auth/otp/request", json={"channel": "sms", "destination": "09350000000"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json().keys() == unknown.json().keys()
    assert len(sender.sent) == 1


def test_code_is_single_use(client: TestClient, sender: CapturingSender, user: User) -> None:
    challenge = request_code(client)
    body = {"challenge_id": challenge, "code": sender.last_code}
    assert client.post("/auth/otp/verify", json=body).status_code == 200
    assert client.post("/auth/otp/verify", json=body).status_code == 400


def test_too_many_wrong_attempts_kill_the_challenge(
    client: TestClient, sender: CapturingSender, user: User
) -> None:
    challenge = request_code(client)
    right = sender.last_code
    wrong = "11111" if right != "11111" else "22222"
    for _ in range(get_settings().otp_max_attempts):
        r = client.post("/auth/otp/verify", json={"challenge_id": challenge, "code": wrong})
        assert r.status_code == 400
    r = client.post("/auth/otp/verify", json={"challenge_id": challenge, "code": right})
    assert r.status_code == 400


def test_code_from_another_channel_or_challenge_is_rejected(
    client: TestClient, sender: CapturingSender, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    codes = iter([12345, 67890])
    monkeypatch.setattr("app.modules.auth.otp.secrets.randbelow", lambda _: next(codes))
    first = request_code(client, "sms", "09121234567")
    second = request_code(client, "email", EMAIL)

    # Requesting by email invalidated the SMS challenge.
    r = client.post("/auth/otp/verify", json={"challenge_id": first, "code": "12345"})
    assert r.status_code == 400
    # The SMS code does not work on the email challenge.
    r = client.post("/auth/otp/verify", json={"challenge_id": second, "code": "12345"})
    assert r.status_code == 400
    r = client.post("/auth/otp/verify", json={"challenge_id": second, "code": "67890"})
    assert r.status_code == 200


def test_expired_code_is_rejected(client: TestClient, sender: CapturingSender, user: User) -> None:
    challenge = request_code(client)
    get_redis().delete(f"otp:challenge:{challenge}")  # what TTL expiry does
    response = client.post(
        "/auth/otp/verify", json={"challenge_id": challenge, "code": sender.last_code}
    )
    assert response.status_code == 400


def test_resend_cooldown(client: TestClient, sender: CapturingSender, user: User) -> None:
    request_code(client)
    again = client.post("/auth/otp/request", json={"channel": "sms", "destination": "09121234567"})
    assert again.status_code == 429
    assert int(again.headers["Retry-After"]) > 0


def test_switching_channel_does_not_reset_account_limit(
    client: TestClient, sender: CapturingSender, user: User
) -> None:
    redis = get_redis()
    redis.set(f"otp:rl:account:{user.id}", get_settings().otp_max_requests_per_account_hour)
    request_code(client, "email", EMAIL)
    assert sender.sent == []  # silently not sent; response unchanged


def test_inactive_user_cannot_log_in(
    client: TestClient, sender: CapturingSender, user: User
) -> None:
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == user.id).values(is_active=False))
        db.commit()
    request_code(client)
    assert sender.sent == []


def test_redis_outage_fails_closed(client: TestClient, sender: CapturingSender, user: User) -> None:
    app.dependency_overrides[get_redis] = lambda: Redis(port=1, socket_connect_timeout=0.2)
    response = client.post(
        "/auth/otp/request", json={"channel": "sms", "destination": "09121234567"}
    )
    assert response.status_code == 503


# -- sessions ------------------------------------------------------------


def test_protected_route_requires_login(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_logout_ends_session_immediately(
    client: TestClient, sender: CapturingSender, user: User
) -> None:
    login(client, sender)
    access = client.cookies.get("crm_access")
    assert client.post("/auth/logout", headers=csrf(client)).status_code == 204

    # The JWT is still unexpired, but the session is gone.
    replay = TestClient(app, cookies={"crm_access": access or ""})
    assert replay.get("/auth/me").status_code == 401


def test_logout_requires_csrf(client: TestClient, sender: CapturingSender, user: User) -> None:
    login(client, sender)
    assert client.post("/auth/logout").status_code == 403


def test_deactivation_ends_all_sessions(
    client: TestClient, sender: CapturingSender, user: User
) -> None:
    login(client, sender)
    with SessionLocal() as db:
        SessionService(db, get_redis(), get_settings()).revoke_all_for_user(user.id, "deactivated")
    assert client.get("/auth/me").status_code == 401


def test_refresh_rotates_token(client: TestClient, sender: CapturingSender, user: User) -> None:
    login(client, sender)
    old_refresh = client.cookies.get("crm_refresh")
    response = client.post("/auth/refresh", headers=csrf(client))
    assert response.status_code == 200
    assert client.cookies.get("crm_refresh") != old_refresh
    assert client.get("/auth/me").status_code == 200


def test_reused_refresh_token_revokes_session(
    client: TestClient, sender: CapturingSender, user: User
) -> None:
    login(client, sender)
    stolen = client.cookies.get("crm_refresh") or ""
    assert client.post("/auth/refresh", headers=csrf(client)).status_code == 200

    # Move the rotation outside the grace window, then replay the old token.
    with SessionLocal() as db:
        db.execute(update(AuthSession).values(rotated_at=datetime.now(UTC) - timedelta(minutes=5)))
        db.commit()
    attacker = TestClient(app, cookies={"crm_refresh": stolen, CSRF_COOKIE: "x"})
    assert attacker.post("/auth/refresh", headers={CSRF_HEADER: "x"}).status_code == 401

    # The legitimate client is logged out too.
    assert client.get("/auth/me").status_code == 401
