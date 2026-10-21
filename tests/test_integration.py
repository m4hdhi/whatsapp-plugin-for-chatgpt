"""Public API + real database and scheduler; only external services are replaced."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

import httpx
from fastapi.testclient import TestClient

from app.core import Engine
from app.server import create_app


def test_selected_group_to_ai_to_persisted_iphone_reminder(tmp_path):
    now = [datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)]
    push_requests = []
    ai_requests = []

    def remote(request):
        if request.url.host == "api.openai.com":
            body = json.loads(request.content)
            assert body["store"] is False
            assert body["text"]["format"]["strict"] is True
            ai_requests.append(body)
            result = {"summary": "Alex must send the project plan by 15:00 Dubai time.", "tasks": [{
                "title": "Send project plan", "assignee_self": True,
                "due_at": "2026-10-20T15:00:00+04:00", "needs_review": False,
                "confidence": .98, "source_ids": ["message-123"],
            }]}
            return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}]})
        if request.url.host == "api.pushover.net":
            push_requests.append(request)
            return httpx.Response(200, json={"status": 1, "request": "accepted-fixture"})
        if request.url.path == "/api/sessions/default":
            return httpx.Response(200, json={"status": "WORKING", "me": {"id": "971500000000@c.us"}})
        return httpx.Response(200, json=[])

    engine = Engine(tmp_path, transport=httpx.MockTransport(remote), clock=lambda: now[0])
    token, hook = "t" * 64, "h" * 64
    headers = {"Authorization": f"Bearer {token}"}
    app = create_app(engine, admin_token=token, webhook_secret=hook, run_scheduler=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        configured = client.post("/api/settings", headers=headers, json={
            "display_name": "Alex", "timezone": "Asia/Dubai", "aliases": ["Al"],
            "selected_groups": [{"id": "120100@g.us", "name": "Project team"}],
            "openai_api_key": "fixture-not-a-real-credential",
            "pushover_token": "p" * 30, "pushover_user": "u" * 30,
            "quiet_start": "22:00", "quiet_end": "08:00", "daily_digest_time": "23:59",
        })
        assert configured.status_code == 200

        def ingest(group, message_id, text):
            body = json.dumps({"session": "default", "event": "message.any", "payload": {
                "id": message_id, "from": group, "fromMe": False, "participant": "Sam",
                "body": text, "timestamp": now[0].timestamp(),
            }}).encode()
            signature = hmac.new(hook.encode(), body, hashlib.sha512).hexdigest()
            return client.post("/webhooks/waha", content=body, headers={"X-Webhook-Hmac": signature})

        assert ingest("private@c.us", "excluded-private", "PRIVATE SHOULD NEVER LEAVE PC").json() == {"accepted": 0}
        assert ingest("120999@g.us", "excluded-group", "UNSELECTED SHOULD NEVER LEAVE PC").json() == {"accepted": 0}
        assert ingest("120100@g.us", "message-123", "Alex, send the project plan by 3pm today.").json() == {"accepted": 1}
        assert ingest("120100@g.us", "message-123", "Alex, send the project plan by 3pm today.").json() == {"accepted": 0}
        response = client.post("/api/analyze", headers=headers)
        assert response.status_code == 200
        assert response.json()["tasks_added"] == 1
        state = client.get("/api/state", headers=headers).json()
        task = state["tasks"][0]
        assert task["evidence"][0]["body"] == "Alex, send the project plan by 3pm today."
        assert task["due_at"] == "2026-10-20T11:00:00+00:00"
        assert state["stats"]["messages_pending"] == 0
        assert "fixture-not-a-real-credential" not in json.dumps(state)
        sent_to_ai = json.dumps(ai_requests)
        assert "PRIVATE SHOULD NEVER" not in sent_to_ai
        assert "UNSELECTED SHOULD NEVER" not in sent_to_ai
        assert "Send project plan" in client.get("/api/export", headers=headers).text

    engine.close()
    # Restart with the same local volume; credentials/task state survive.
    engine = Engine(tmp_path, transport=httpx.MockTransport(remote), clock=lambda: now[0])
    now[0] = datetime(2026, 10, 20, 10, 30, tzinfo=timezone.utc)
    engine.tick()
    assert len(push_requests) == 1
    assert engine.state()["notifications"][0]["status"] == "sent"
    engine.tick()
    assert len(push_requests) == 1
    engine.task_update(task["id"], {"status": "done"})
    now[0] += timedelta(minutes=1)
    engine.tick()
    assert len(push_requests) == 1
    engine.close()
