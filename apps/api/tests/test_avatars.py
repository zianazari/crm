"""Profile photos."""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import Org, login_as

WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_set_serve_and_remove_own_photo(org: Org) -> None:
    rep = login_as(org.rep1.id)
    r = rep.put("/users/me/avatar", content=WEBP, headers={"Content-Type": "image/webp"})
    assert r.status_code == 200, r.text
    assert r.json()["avatar_version"] == 1
    assert rep.get("/auth/me").json()["avatar_version"] == 1

    # Others see it, with a long cache, under their own session.
    other = login_as(org.rep2.id)
    photo = other.get(f"/users/{org.rep1.id}/avatar")
    assert photo.status_code == 200 and photo.content == WEBP
    assert photo.headers["content-type"] == "image/webp"
    assert "immutable" in photo.headers["cache-control"]
    assert photo.headers["x-content-type-options"] == "nosniff"
    # And it travels with the person wherever they are referenced.
    manager = login_as(org.manager.id)
    users = {u["id"]: u for u in manager.get("/users/assignable").json()}
    assert users[str(org.rep1.id)]["avatar_version"] == 1

    r = rep.put("/users/me/avatar", content=PNG, headers={"Content-Type": "image/png"})
    assert r.json()["avatar_version"] == 2
    assert rep.delete("/users/me/avatar").json()["avatar_version"] is None
    assert other.get(f"/users/{org.rep1.id}/avatar").status_code == 404


def test_only_small_real_images(org: Org) -> None:
    rep = login_as(org.rep1.id)

    def put(body: bytes, kind: str) -> int:
        r = rep.put("/users/me/avatar", content=body, headers={"Content-Type": kind})
        return int(r.status_code)

    assert put(WEBP, "image/svg+xml") == 415
    assert put(b"<svg onload=alert(1)>", "image/png") == 422  # wrong signature
    assert put(WEBP[:12] + b"\x00" * (201 * 1024), "image/webp") == 413
    assert TestClient(app).get(f"/users/{org.rep1.id}/avatar").status_code == 401
    no_csrf = login_as(org.rep1.id)
    no_csrf.headers.pop("X-CSRF-Token")
    assert (
        no_csrf.put(
            "/users/me/avatar", content=WEBP, headers={"Content-Type": "image/webp"}
        ).status_code
        == 403
    )
