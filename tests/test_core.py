from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.core import Engine


class Time:
    def __init__(self):
        self.now = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def configured(tmp_path, handler=None, clock=None):
    engine = Engine(tmp_path, transport=httpx.MockTransport(handler or (lambda r: httpx.Response(200, json={}))), clock=clock or Time())
    engine.update_settings({"display_name": "Alex", "selected_groups": [{"id": "123@g.us", "name": "Work"}], "openai_api_key": "sk-test-secret"})
    return engine


def message(mid="msg1", body="Alex, please send the report tomorrow at 3 pm", group="123@g.us"):
    return {"id": mid, "from": group, "participant": "1@c.us", "body": body, "timestamp": 1792483200}


def response(task=None, summary="Report requested"):
    result = {"summary": summary, "tasks": [task or {"title": "Send the report", "assignee_self": True, "due_at": "2026-10-21T15:00:00+04:00", "source_ids": ["msg1"], "confidence": 0.95, "needs_review": False}]}
    return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}]}


def test_only_allowlisted_group_text_is_stored_and_unique_across_restart(tmp_path):
    engine = configured(tmp_path)
    assert engine.ingest_event({"event": "message.any", "payload": message()}) == 1
    assert engine.ingest_event({"event": "message.any", "payload": message()}) == 0
    assert engine.ingest_event({"event": "message.any", "payload": message("private", "PRIVATE-MARKER", "99@c.us")}) == 0
    assert engine.ingest_messages("999@g.us", [message("unselected", "UNSELECTED-MARKER")]) == 0
    engine.close()
    engine = configured(tmp_path)
    assert engine.state()["stats"]["messages_pending"] == 1
    assert "sk-test-secret" not in json.dumps(engine.state())
    assert b"PRIVATE-MARKER" not in (tmp_path / "assistant.sqlite3").read_bytes()


def test_analysis_uses_responses_and_retains_inspectable_evidence(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response())
    engine = configured(tmp_path, handler)
    engine.ingest_event({"event": "message.any", "payload": message()})
    result = engine.analyze()
    assert result["processed"] == 1
    state = engine.state()
    assert state["stats"]["messages_pending"] == 0
    assert state["tasks"][0]["evidence"][0]["body"].startswith("Alex,")
    request = json.loads(calls[0].content)
    assert calls[0].url.path == "/v1/responses"
    assert request["store"] is False
    assert request["text"]["format"]["strict"] is True
    engine.close()
    restored = configured(tmp_path, handler)
    assert restored.state()["tasks"][0]["title"] == "Send the report"


@pytest.mark.parametrize("bad", ["api", "evidence", "incomplete"])
def test_failed_or_ungrounded_analysis_keeps_pending(tmp_path, bad):
    data = response()
    if bad == "evidence":
        task = json.loads(data["output"][0]["content"][0]["text"])
        task["tasks"][0]["source_ids"] = ["invented"]
        data["output"][0]["content"][0]["text"] = json.dumps(task)
    if bad == "incomplete":
        data["status"] = "incomplete"
    engine = configured(tmp_path, lambda r: httpx.Response(429 if bad == "api" else 200, json=data))
    engine.ingest_messages("123@g.us", [message()])
    with pytest.raises(RuntimeError):
        engine.analyze()
    assert engine.state()["stats"]["messages_pending"] == 1
    assert engine.state()["tasks"] == []
    assert engine.state()["stats"]["analyses_today"] == 1


def test_uncertain_deadline_requires_review_and_user_confirmation(tmp_path):
    task = {"title": "Send report", "assignee_self": True, "due_at": None, "source_ids": ["msg1"], "confidence": .9, "needs_review": True}
    engine = configured(tmp_path, lambda r: httpx.Response(200, json=response(task)))
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    item = engine.state()["tasks"][0]
    assert item["needs_review"] is True
    assert item["reminder_at"] is None
    changed = engine.task_update(item["id"], {"due_at": "2026-10-21T15:00:00+04:00", "needs_review": False})
    assert changed["needs_review"] is False
    assert changed["reminder_at"] == "2026-10-21T10:30:00+00:00"


def test_quiet_hours_defer_reminder_and_failed_push_retries(tmp_path):
    clock = Time()
    clock.now = datetime(2026, 10, 20, 18, 30, tzinfo=timezone.utc)  # 22:30 Dubai
    pushes = []
    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json=response(task={"title": "Send report", "assignee_self": True, "due_at": "2026-10-20T23:00:00+04:00", "source_ids": ["msg1"], "confidence": .95, "needs_review": False}))
        if request.url.host == "api.pushover.net":
            pushes.append(request)
            return httpx.Response(503 if len(pushes) == 1 else 200, json={"status": 0 if len(pushes) == 1 else 1})
        return httpx.Response(200, json={"status": "STOPPED"})
    engine = configured(tmp_path, handler, clock)
    engine.update_settings({"timezone": "Asia/Dubai", "quiet_start": "22:00", "quiet_end": "08:00", "pushover_token": "token", "pushover_user": "user", "daily_digest_time": "23:59"})
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    engine.tick()
    assert pushes == []
    clock.now = datetime(2026, 10, 21, 4, 0, tzinfo=timezone.utc)
    engine.tick()
    assert len(pushes) == 1
    notice = engine.state()["notifications"][0]
    assert notice["status"] == "pending"
    clock.now += timedelta(minutes=10)
    engine.tick()
    assert len(pushes) == 2
    assert engine.state()["notifications"][0]["status"] == "sent"
    engine.tick()
    assert len(pushes) == 2


def test_demo_never_calls_network(tmp_path):
    def network(_):
        pytest.fail("demo must not contact network")
    engine = Engine(tmp_path, demo=True, transport=httpx.MockTransport(network), clock=Time())
    assert engine.state()["demo"] is True
    assert engine.state()["tasks"]
    engine.list_groups()
    engine.connect()
    engine.qr()
    engine.tick()


def test_settings_validation_budget_and_secret_clearing(tmp_path):
    engine = configured(tmp_path)
    for payload in ({"timezone": "Bad/Zone"}, {"selected_groups": [{"id": "person@c.us", "name": "bad"}]}, {"daily_digest_time": "25:30"}, {"max_calls_per_day": 0}, {"model": "bad model!"}):
        with pytest.raises(ValueError):
            engine.update_settings(payload)
    assert engine.state()["configured"]["openai"] is True
    engine.update_settings({"clear_secrets": ["openai_api_key"]})
    assert engine.state()["configured"]["openai"] is False


def test_permanent_push_rejection_does_not_retry(tmp_path):
    clock = Time()
    pushes = []
    def handler(request):
        if request.url.host == "api.pushover.net":
            pushes.append(request)
            return httpx.Response(400, json={"status": 0, "errors": ["invalid user"]})
        return httpx.Response(200, json={"status": "STOPPED"})
    engine = configured(tmp_path, handler, clock)
    engine.update_settings({"pushover_token": "token", "pushover_user": "user"})
    with pytest.raises(RuntimeError):
        engine.test_notification()
    clock.now += timedelta(hours=1)
    engine.tick()
    assert len(pushes) == 1
    assert engine.state()["notifications"][0]["status"] == "failed"


def test_api_daily_limit_survives_restart_and_day_rollover(tmp_path):
    clock = Time()
    engine = configured(tmp_path, lambda r: httpx.Response(500), clock)
    engine.update_settings({"max_calls_per_day": 1})
    engine.ingest_messages("123@g.us", [message()])
    with pytest.raises(RuntimeError):
        engine.analyze()
    engine.close()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response())
    engine = configured(tmp_path, handler, clock)
    with pytest.raises(RuntimeError, match="Daily AI call limit"):
        engine.analyze()
    assert calls == []
    clock.now += timedelta(days=1)
    assert engine.analyze()["processed"] == 1


def test_outgoing_commitment_preserved_and_naive_due_date_rejected(tmp_path):
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=response())
    engine = configured(tmp_path, handler)
    raw = message(body="I will send this tomorrow at 3 pm")
    raw.update({"from": "me@c.us", "to": "123@g.us", "fromMe": True})
    assert engine.ingest_event({"event": "message.any", "payload": raw}) == 1
    engine.analyze()
    data = json.loads(captured[0]["input"][1]["content"])
    assert data["messages"][0]["from_me"] is True
    with pytest.raises(ValueError):
        engine.task_update(engine.state()["tasks"][0]["id"], {"due_at": "2026-10-21T15:00:00"})


def test_deselection_purges_raw_messages_and_stops_reminders(tmp_path):
    clock = Time()
    engine = configured(tmp_path, lambda r: httpx.Response(200, json=response()), clock)
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    engine.update_settings({"selected_groups": []})
    state = engine.state()
    assert state["summaries"] == []
    assert state["tasks"][0]["evidence"] == []
    clock.now += timedelta(days=2)
    engine.tick()
    assert state["tasks"][0]["group_name"] == "Removed group"
    assert not any(n["id"].startswith("task:") for n in engine.state()["notifications"])


def test_snooze_rearms_sent_reminder_and_survives_restart(tmp_path):
    clock = Time()
    engine = configured(tmp_path, lambda r: httpx.Response(200, json=response()), clock)
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    task_id = engine.state()["tasks"][0]["id"]
    task = engine.task_update(task_id, {"snooze_minutes": 60})
    assert task["reminder_at"] == "2026-10-20T09:00:00+00:00"
    engine.close()
    engine = configured(tmp_path, clock=clock)
    assert engine.state()["tasks"][0]["reminder_at"] == "2026-10-20T09:00:00+00:00"
    for invalid in (0, True, 10081, "60"):
        with pytest.raises(ValueError):
            engine.task_update(task_id, {"snooze_minutes": invalid})


def test_changed_deadline_is_proposed_for_review_not_silently_ignored(tmp_path):
    results = [response(), response(task={"title": "Send the report", "assignee_self": True, "due_at": "2026-10-22T15:00:00+04:00", "source_ids": ["msg2"], "confidence": .98, "needs_review": False})]
    engine = configured(tmp_path, lambda r: httpx.Response(200, json=results.pop(0) if r.url.host == "api.openai.com" else {"status": "STOPPED"}))
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    engine.ingest_messages("123@g.us", [message("msg2", "Alex, the report deadline moved to Thursday at 3pm")])
    engine.analyze()
    tasks = engine.state()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["due_at"] == "2026-10-22T11:00:00+00:00"
    assert tasks[0]["needs_review"] is True
    assert tasks[0]["reminder_at"] is None


def test_mentions_and_linked_owner_ids_reach_ai_without_raw_payload(tmp_path):
    captured = []
    def handler(request):
        if request.url.host == "api.openai.com":
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=response())
        return httpx.Response(200, json={"status": "WORKING", "me": {"id": "123@c.us", "lid": "456@lid"}})
    engine = configured(tmp_path, handler)
    engine.connect()
    raw = message()
    raw["_data"] = {"mentionedJidList": ["456@lid"], "secret_unnecessary_payload": "DO_NOT_STORE"}
    engine.ingest_messages("123@g.us", [raw])
    engine.analyze()
    text = captured[0]["input"][1]["content"]
    user_data = json.loads(text)
    assert user_data["messages"][0]["mentions_owner"] is True
    assert "DO_NOT_STORE" not in text


def test_daily_digest_is_once_per_local_day_across_restart(tmp_path):
    clock = Time()
    pushes = []
    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json=response())
        if request.url.host == "api.pushover.net":
            pushes.append(request)
            return httpx.Response(200, json={"status": 1})
        return httpx.Response(200, json={"status": "STOPPED"})
    engine = configured(tmp_path, handler, clock)
    engine.update_settings({"pushover_token": "token", "pushover_user": "user"})
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    engine.tick()
    assert len(pushes) == 1  # noon Dubai, after daily 09:00
    engine.close()
    engine = configured(tmp_path, handler, clock)
    engine.tick()
    assert len(pushes) == 1


def test_low_confidence_and_other_peoples_tasks_never_create_reminders(tmp_path):
    other = {"title": "Someone else's report", "assignee_self": False, "due_at": "2026-10-21T15:00:00+04:00", "source_ids": ["msg1"], "confidence": .99, "needs_review": False}
    low = {**other, "title": "Possible task", "assignee_self": True, "confidence": .4}
    data = response(other)
    decoded = json.loads(data["output"][0]["content"][0]["text"])
    decoded["tasks"].append(low)
    data["output"][0]["content"][0]["text"] = json.dumps(decoded)
    engine = configured(tmp_path, lambda r: httpx.Response(200, json=data))
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    assert engine.state()["tasks"] == []


def test_private_and_unselected_groups_never_requested_in_recovery(tmp_path):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/api/sessions/default":
            return httpx.Response(200, json={"status": "WORKING"})
        return httpx.Response(200, json=[])
    engine = configured(tmp_path, handler)
    engine.tick()
    histories = [url for url in calls if "/chats/" in url]
    assert len(histories) == 1
    assert "123%40g.us" in histories[0]


def test_manual_test_does_not_flush_quiet_hour_backlog(tmp_path):
    clock = Time()
    clock.now = datetime(2026, 10, 20, 18, 30, tzinfo=timezone.utc)
    pushes = []
    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json=response(task={"title": "Send report", "assignee_self": True, "due_at": "2026-10-20T23:00:00+04:00", "source_ids": ["msg1"], "confidence": .95, "needs_review": False}))
        if request.url.host == "api.pushover.net":
            pushes.append(request)
            return httpx.Response(200, json={"status": 1})
        return httpx.Response(200, json={"status": "STOPPED"})
    engine = configured(tmp_path, handler, clock)
    engine.update_settings({"pushover_token": "token", "pushover_user": "user"})
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    engine.tick()
    assert pushes == []
    engine.test_notification()
    assert len(pushes) == 1
    assert all(n["status"] == "pending" for n in engine.state()["notifications"] if not n["id"].startswith("test:"))


def test_empty_morning_does_not_suppress_later_first_digest(tmp_path):
    clock = Time()
    engine = configured(tmp_path, lambda r: httpx.Response(200, json=response()), clock)
    engine.tick()
    assert engine.state()["notifications"] == []
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    engine.tick()
    assert len([n for n in engine.state()["notifications"] if n["id"].startswith("digest:")]) == 1


def test_network_disconnect_queues_visible_alert(tmp_path):
    clock = Time()
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"status": "WORKING"})
        raise httpx.ConnectError("deliberately unavailable secret-host", request=request)
    engine = configured(tmp_path, handler, clock)
    engine.connect()
    engine.tick()
    clock.now += timedelta(seconds=60)
    engine.tick()
    state = engine.state()
    assert state["connection"]["status"] == "unavailable"
    assert any(n["id"].startswith("connection:") for n in state["notifications"])
    assert "secret-host" not in json.dumps(state)


def test_changing_lead_time_cancels_stale_queued_reminder(tmp_path):
    clock = Time()
    clock.now = datetime(2026, 10, 20, 18, 30, tzinfo=timezone.utc)
    engine = configured(tmp_path, lambda r: httpx.Response(200, json=response()), clock)
    engine.update_settings({"remind_before_minutes": 1020})
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    task_id = engine.state()["tasks"][0]["id"]
    engine.tick()
    assert any(n["id"].startswith("task:" + task_id) for n in engine.state()["notifications"])
    engine.update_settings({"remind_before_minutes": 0})
    assert not any(n["id"].startswith("task:" + task_id) for n in engine.state()["notifications"])


@pytest.mark.parametrize("status", [404, 500])
def test_non_success_session_status_queues_disconnect_alert(tmp_path, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200 if len(calls) == 1 else status, json={"status": "WORKING"})
    engine = configured(tmp_path, handler)
    engine.connect()
    engine.tick()
    engine.clock.now += timedelta(seconds=60)
    engine.tick()
    assert any(n["id"].startswith("connection:") for n in engine.state()["notifications"])


def test_removed_groups_cannot_hide_selected_tasks_in_daily_digest(tmp_path):
    base = {"assignee_self": True, "due_at": "2026-10-20T15:00:00+04:00", "source_ids": ["msg1"], "confidence": .95, "needs_review": False}
    first = response()
    first["output"][0]["content"][0]["text"] = json.dumps({"summary": "Old group", "tasks": [{**base, "title": f"Old task {n}"} for n in range(30)]})
    second = response({**base, "title": "Current task", "due_at": "2026-10-21T15:00:00+04:00", "source_ids": ["msg2"]})
    results = [first, second]
    engine = configured(tmp_path, lambda r: httpx.Response(200, json=results.pop(0) if r.url.host == "api.openai.com" else {"status": "STOPPED"}))
    engine.ingest_messages("123@g.us", [message()])
    engine.analyze()
    engine.update_settings({"selected_groups": [{"id": "456@g.us", "name": "Current"}]})
    engine.ingest_messages("456@g.us", [message("msg2", "Alex please finish Current task", "456@g.us")])
    engine.analyze()
    engine.tick()
    digest = next(n for n in engine.state()["notifications"] if n["id"].startswith("digest:"))
    assert "1 open tasks" in digest["body"]
    assert "Current task" in digest["body"]
    assert "Old task" not in digest["body"]
