"""Real authenticated API and SQLite; external services use synthetic fixtures."""
from datetime import datetime, timezone
import hashlib
import hmac
import json

import httpx
from fastapi.testclient import TestClient

from app.core import Engine
from app.server import create_app


def test_chat_permissions_and_private_content_through_public_api(tmp_path):
    now = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
    metadata_requests, ai_requests = [], []

    def remote(request):
        if request.url.path == "/api/default/chats":
            metadata_requests.append(request)
            return httpx.Response(200, json=[
                {"id": "sam@c.us", "name": "Sam", "type": "private", "isGroup": False},
                {"id": "work@g.us", "name": "Work", "type": "group", "isGroup": True},
            ])
        if request.url.host == "api.openai.com":
            ai_requests.append(json.loads(request.content))
            result = {"summary": "An invoice is needed tomorrow.", "tasks": [{
                "title": "Send the invoice", "assignee_self": True,
                "due_at": "2026-10-21T15:00:00+04:00", "needs_review": False,
                "confidence": .98, "source_ids": ["private-1"],
            }]}
            return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}]})
        return httpx.Response(200, json={"status": "WORKING"})

    engine = Engine(tmp_path, transport=httpx.MockTransport(remote), clock=lambda: now)
    token, hook = "t" * 64, "h" * 64
    headers = {"Authorization": f"Bearer {token}"}
    app = create_app(engine, admin_token=token, webhook_secret=hook, run_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/chats").status_code == 401
        response = client.get("/api/chats", headers=headers)
        assert response.status_code == 200
        assert {c["type"] for c in response.json()["chats"]} == {"group", "private"}
        assert metadata_requests[0].url.params["metadataOnly"] == "true"
        assert not ai_requests
        assert client.post("/api/settings", headers=headers, json={"monitoring_mode": "all"}).status_code == 400

        def ingest(chat, mid, text):
            body = json.dumps({"session": "default", "event": "message.any", "payload": {
                "id": mid, "from": chat, "to": "self@c.us", "fromMe": False,
                "body": text, "timestamp": now.timestamp(),
            }}).encode()
            signature = hmac.new(hook.encode(), body, hashlib.sha512).hexdigest()
            return client.post("/webhooks/waha", content=body, headers={"X-Webhook-Hmac": signature})

        assert ingest("sam@c.us", "before", "Please send the invoice.").json() == {"accepted": 0}
        assert client.post("/api/settings", headers=headers, json={
            "monitoring_mode": "all", "processing_consent": True,
            "excluded_chat_ids": ["excluded@c.us"], "openai_api_key": "synthetic-test-key",
        }).status_code == 200
        assert ingest("excluded@c.us", "excluded", "EXCLUDED CONTENT").json() == {"accepted": 0}
        assert ingest("status@broadcast", "status", "STATUS CONTENT").json() == {"accepted": 0}
        text = "Can you send the invoice tomorrow at 3pm?"
        assert ingest("sam@c.us", "private-1", text).json() == {"accepted": 1}
        assert client.post("/api/analyze", headers=headers).json()["tasks_added"] == 1
        state = client.get("/api/state", headers=headers).json()
        assert state["tasks"][0]["chat_type"] == "private"
        assert state["tasks"][0]["evidence"][0]["body"] == text
        supplied = json.loads(ai_requests[0]["input"][1]["content"])
        assert supplied["chat_type"] == "private" and supplied["owner_is_recipient"] is True
        assert "EXCLUDED CONTENT" not in json.dumps(ai_requests)
        assert ai_requests[0]["store"] is False

        assert client.post("/api/settings", headers=headers, json={"processing_consent": False}).status_code == 200
        assert ingest("sam@c.us", "after", "PRIVATE AFTER PAUSE").json() == {"accepted": 0}
        assert client.post("/api/analyze", headers=headers).json()["processed"] == 0
        state = client.get("/api/state", headers=headers).json()
        assert state["summaries"] == [] and state["tasks"][0]["evidence"] == []
        assert state["stats"]["monitoring_allowed"] is False and len(ai_requests) == 1
    engine.close()


def test_chat_api_fails_closed_without_metadata_extension(tmp_path):
    requests = []
    def remote(request):
        requests.append(request)
        return httpx.Response(200, json=[{"id": "sam@c.us", "name": "Sam", "lastMessage": {"body": "SHOULD NOT BE RETURNED"}}])
    engine = Engine(tmp_path, transport=httpx.MockTransport(remote))
    token = "t" * 64
    app = create_app(engine, admin_token=token, webhook_secret="h" * 64, run_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/api/chats", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 503 and "extension unavailable" in response.json()["detail"]
        assert "SHOULD NOT BE RETURNED" not in response.text
        assert len(requests) == 1 and requests[0].url.params["metadataOnly"] == "true"
        assert engine.state()["stats"]["messages_pending"] == 0
    engine.close()
