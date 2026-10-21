import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.server import create_app

TOKEN = "a" * 64
HOOK = "b" * 64


class FakeEngine:
    def __init__(self):
        self.events = []
        self.desktop_notify = None

    def state(self):
        return {"settings": {}, "configured": {}, "demo": True}

    def ingest_event(self, event):
        self.events.append(event)
        return 1

    def update_settings(self, payload):
        if "unknown" in payload:
            raise ValueError("Unknown setting.")

    def analyze(self):
        raise RuntimeError("Connect an OpenAI API key in Settings first.")

    def export_markdown(self):
        return "# My brief\n"


@pytest.fixture
def client():
    engine = FakeEngine()
    app = create_app(engine, admin_token=TOKEN, webhook_secret=HOOK, run_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.engine = engine
        yield client


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_private_data_requires_sign_in(client):
    assert client.get("/api/state").status_code == 401
    response = client.get("/api/state", headers=auth())
    assert response.status_code == 200
    assert response.json()["demo"] is True
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_dns_rebinding_and_cross_origin_writes_blocked(client):
    assert client.get("/health", headers={"Host": "attacker.invalid"}).status_code == 403
    response = client.post("/api/settings", headers={**auth(), "Origin": "https://attacker.invalid"}, json={})
    assert response.status_code == 403


def test_only_signed_webhook_is_accepted(client):
    payload = b'{"event":"message.any","payload":{"id":"msg-1"}}'
    assert client.post("/webhooks/waha", content=payload).status_code == 401
    signature = hmac.new(HOOK.encode(), payload, hashlib.sha512).hexdigest()
    headers = {"X-Webhook-Hmac": signature, "X-Webhook-Hmac-Algorithm": "sha512", "Content-Type": "application/json"}
    response = client.post("/webhooks/waha", content=payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"accepted": 1}
    assert client.engine.events == [json.loads(payload)]
    # HMAC is over exact raw bytes, not an equivalent reserialized JSON object.
    assert client.post("/webhooks/waha", content=payload + b" ", headers=headers).status_code == 401


def test_bad_json_signed_webhook_is_rejected(client):
    payload = b"not-json"
    signature = hmac.new(HOOK.encode(), payload, hashlib.sha512).hexdigest()
    assert client.post("/webhooks/waha", content=payload, headers={"X-Webhook-Hmac": signature}).status_code == 400


def test_request_body_is_bounded(client):
    assert client.post("/api/settings", headers=auth(), content=b"x" * 1_048_577).status_code == 413


def test_safe_actionable_errors_and_export(client):
    assert client.post("/api/settings", headers=auth(), json={"unknown": 1}).status_code == 400
    response = client.post("/api/analyze", headers=auth())
    assert response.status_code == 503
    assert response.json()["detail"] == "Connect an OpenAI API key in Settings first."
    exported = client.get("/api/export", headers=auth())
    assert exported.text == "# My brief\n"
    assert "attachment" in exported.headers["content-disposition"]


def test_no_developer_docs_or_tokens_in_static_page(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    response = client.get("/")
    assert response.status_code == 200
    assert TOKEN not in response.text
    assert HOOK not in response.text


def test_startup_rejects_default_or_missing_credentials():
    with pytest.raises(RuntimeError, match="Start.cmd"):
        create_app(FakeEngine(), admin_token="", webhook_secret="", run_scheduler=False)
