"""Local SMS provider simulator for development and tests. Never used in production.

* POST /send {to, text, idempotency_key, callback_url} -> {"message_id": ...}
  The same idempotency key returns the original message instead of sending twice.
* A signed delivery report (X-Signature: hex HMAC-SHA256 of the body) is POSTed to
  callback_url about a second later.
* Behaviour by the last digits of the number, to exercise failure handling:
    ...9404  delivery report "failed"
    ...9503  HTTP 503 (temporary provider outage)
    ...9408  accepts the message but never answers (client times out: "unknown")
* GET /           RTL page listing received messages (auto-refresh)
* GET /api/messages  the same as JSON (used by end-to-end scripts)
* DELETE /api/messages  clear the inbox
"""

import asyncio
import hashlib
import hmac
import json
import os
import uuid
from datetime import UTC, datetime
from html import escape

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

SECRET = os.environ.get("SMS_SINK_WEBHOOK_SECRET", "dev-only-sms-webhook-secret")
app = FastAPI(title="sms-sink")
messages: list[dict[str, object]] = []
by_key: dict[str, dict[str, object]] = {}


class SendIn(BaseModel):
    to: str
    text: str
    idempotency_key: str | None = None
    callback_url: str | None = None


async def report(message: dict[str, object], callback_url: str) -> None:
    await asyncio.sleep(1)
    status = "failed" if str(message["to"]).endswith("9404") else "delivered"
    message["status"] = status
    body = json.dumps(
        {"event_id": uuid.uuid4().hex, "message_id": message["id"], "status": status},
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                callback_url,
                content=body,
                headers={"Content-Type": "application/json", "X-Signature": signature},
            )
    except httpx.HTTPError as exc:
        message["callback_error"] = str(exc)


@app.post("/send")
async def send(body: SendIn) -> dict[str, object]:
    if body.idempotency_key and body.idempotency_key in by_key:
        return {"message_id": by_key[body.idempotency_key]["id"], "duplicate": True}
    if body.to.endswith("9503"):
        raise HTTPException(503, "simulated provider outage")
    message: dict[str, object] = {
        "id": uuid.uuid4().hex,
        "to": body.to,
        "text": body.text,
        "status": "accepted",
        "at": datetime.now(UTC).isoformat(),
    }
    messages.insert(0, message)
    if body.idempotency_key:
        by_key[body.idempotency_key] = message
    if body.to.endswith("9408"):
        await asyncio.sleep(30)  # accepted, but the client gives up waiting
    if body.callback_url:
        asyncio.create_task(report(message, body.callback_url))
    return {"message_id": message["id"]}


@app.get("/api/messages")
def list_messages() -> list[dict[str, object]]:
    return messages


@app.delete("/api/messages")
def clear() -> dict[str, int]:
    count = len(messages)
    messages.clear()
    by_key.clear()
    return {"cleared": count}


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    rows = "".join(
        f"<tr><td dir='ltr'>{escape(str(m['to']))}</td><td>{escape(str(m['text']))}</td>"
        f"<td>{escape(str(m['status']))}</td><td dir='ltr'>{escape(str(m['at']))[:19]}</td></tr>"
        for m in messages
    )
    return f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="3"><title>sms-sink</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;background:#fafaf9;color:#1c1917}}
table{{border-collapse:collapse;width:100%;background:#fff}}td,th{{border:1px solid #e7e5e4;padding:.5rem;text-align:start}}
h1{{font-size:1.25rem}}p{{color:#57534e}}</style></head><body>
<h1>صندوق پیامک آزمایشی (sms-sink)</h1>
<p>پیامک‌هایی که CRM در محیط توسعه ارسال می‌کند اینجا نمایش داده می‌شوند. هیچ پیامکی واقعاً ارسال نمی‌شود.</p>
<table><thead><tr><th>گیرنده</th><th>متن</th><th>وضعیت</th><th>زمان</th></tr></thead>
<tbody>{rows or "<tr><td colspan=4>پیامی دریافت نشده است.</td></tr>"}</tbody></table></body></html>"""
