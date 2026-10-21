"""Consent, all-chat capture, cross-chat isolation and recovery regressions."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import httpx
import pytest

from app.core import Engine


class Time:
    def __init__(self):
        self.now = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
    def __call__(self):
        return self.now


def msg(chat="111@c.us", mid="one", body="Please send the invoice tomorrow at 3pm", timestamp=1792483200, own=False):
    return {"id": mid, "from": "self@c.us" if own else chat, "to": chat if own else "self@c.us", "fromMe": own, "body": body, "timestamp": timestamp, "pushName": "Sam"}


def single(mid="one"):
    return {"summary": "Invoice requested", "tasks": [{"title": "Send invoice", "assignee_self": True, "due_at": "2026-10-21T15:00:00+04:00", "source_ids": [mid], "confidence": .95, "needs_review": False}]}


def api(value):
    return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(value)}]}]}


def create(tmp_path, handler=None, clock=None):
    engine = Engine(tmp_path, clock=clock or Time(), transport=httpx.MockTransport(handler or (lambda r: httpx.Response(200, json={"status": "STOPPED"})) ))
    engine.update_settings({"openai_api_key": "sk-test-only"})
    return engine


def all_chats(engine):
    return engine.update_settings({"monitoring_mode": "all", "processing_consent": True})


def test_all_private_and_future_chats_require_explicit_new_consent(tmp_path):
    engine = create(tmp_path)
    assert engine.settings()["processing_consent"] is False
    assert engine.ingest_event({"event": "message.any", "payload": msg()}) == 0
    with pytest.raises(ValueError):
        engine.update_settings({"monitoring_mode": "all"})
    engine.update_settings({"selected_groups": [{"id": "work@g.us", "name": "Work"}]})
    with pytest.raises(ValueError):
        engine.update_settings({"monitoring_mode": "all"})  # group permission cannot silently widen
    all_chats(engine)
    assert engine.ingest_event({"event": "message.any", "payload": msg()}) == 1
    assert engine.ingest_event({"event": "message.any", "payload": msg("new@lid", "two", own=True)}) == 1
    assert engine.state()["stats"]["monitored_chats"] >= 2
    for invalid in ("status@broadcast", "news@newsletter", "x@broadcast", "not-a-chat", ""):
        assert engine.ingest_event({"event": "message.any", "payload": msg(invalid, invalid or "invalid")}) == 0


def test_selected_private_excluded_and_revoked_scope_is_purged(tmp_path):
    engine = create(tmp_path, lambda r: httpx.Response(200, json=api(single())))
    with pytest.raises(ValueError):
        engine.update_settings({"selected_chats": [{"id": "111@c.us", "name": "Sam", "type": "private"}]})
    engine.update_settings({"selected_chats": [{"id": "111@c.us", "name": "Sam", "type": "private"}], "processing_consent": True})
    assert engine.ingest_event({"event": "message.any", "payload": msg("other@c.us", "other")}) == 0
    assert engine.ingest_event({"event": "message.any", "payload": msg()}) == 1
    engine.analyze()
    task = engine.state()["tasks"][0]
    assert task["chat_type"] == "private" and task["chat_id"] == "111@c.us"
    engine.update_settings({"processing_consent": False})
    state = engine.state()
    assert state["stats"]["monitoring_allowed"] is False
    assert state["stats"]["messages_pending"] == 0
    assert state["summaries"] == [] and state["tasks"][0]["evidence"] == []
    assert engine.ingest_event({"event": "message.any", "payload": msg(mid="after")}) == 0
    assert engine.analyze()["processed"] == 0


def test_allmode_exclusion_and_scope_start_prevent_old_history(tmp_path):
    engine = create(tmp_path)
    all_chats(engine)
    assert engine.ingest_messages("111@c.us", [msg(timestamp=1792479600)]) == 0
    assert engine.ingest_messages("111@c.us", [msg()]) == 1
    engine.update_settings({"excluded_chat_ids": ["111@c.us"]})
    assert engine.state()["stats"]["messages_pending"] == 0
    assert engine.ingest_messages("111@c.us", [msg(mid="again")]) == 0
    assert engine.ingest_messages("222@s.whatsapp.net", [msg("222@s.whatsapp.net", "future")]) == 1


def test_legacy_saved_groups_migrate_without_private_scope_widening(tmp_path):
    db = sqlite3.connect(tmp_path / "assistant.sqlite3")
    db.execute("CREATE TABLE kv(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    db.execute("INSERT INTO kv VALUES (?,?)", ("settings", json.dumps({"selected_groups": [{"id": "work@g.us", "name": "Work"}]})))
    db.commit()
    db.close()
    engine = create(tmp_path)
    settings = engine.settings()
    assert settings["monitoring_mode"] == "selected" and settings["processing_consent"] is True
    assert settings["selected_chats"] == [{"id": "work@g.us", "name": "Work", "type": "group"}]
    assert engine.ingest_messages("work@g.us", [msg("work@g.us")]) == 1
    assert engine.ingest_messages("111@c.us", [msg(mid="private")]) == 0
    engine.close()
    restored = create(tmp_path)
    assert restored.settings()["selected_chats"] == settings["selected_chats"]


def test_multichat_single_call_private_context_and_atomic_evidence_isolation(tmp_path):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=api({"chats": [{"chat_id": "111@c.us", **single()}, {"chat_id": "work@g.us", **single("two")}]}))
    engine = create(tmp_path, handler)
    all_chats(engine)
    engine.ingest_messages("111@c.us", [msg()])
    engine.ingest_messages("work@g.us", [msg("work@g.us", "two")])
    result = engine.analyze()
    assert result["processed"] == 2 and len(requests) == 1
    assert engine.state()["stats"]["analyses_today"] == 1
    supplied = json.loads(requests[0]["input"][1]["content"])
    private = next(x for x in supplied["chats"] if x["chat_id"] == "111@c.us")
    assert private["chat_type"] == "private" and private["owner_is_recipient"] is True
    assert requests[0]["text"]["format"]["schema"]["properties"]["chats"]
    assert {s["chat_id"] for s in engine.state()["summaries"]} == {"111@c.us", "work@g.us"}


@pytest.mark.parametrize("bad", ["cross_cite", "missing_chat", "duplicate_chat", "unknown_chat", "network"])
def test_multichat_failure_keeps_every_message_pending(tmp_path, bad):
    items = [{"chat_id": "111@c.us", **single()}, {"chat_id": "222@lid", **single("two")}]
    if bad == "cross_cite":
        items[0]["tasks"][0]["source_ids"] = ["two"]
    if bad == "missing_chat":
        items.pop()
    if bad == "duplicate_chat":
        items[1]["chat_id"] = items[0]["chat_id"]
    if bad == "unknown_chat":
        items[1]["chat_id"] = "unknown@c.us"
    engine = create(tmp_path, lambda r: httpx.Response(500 if bad == "network" else 200, json=api({"chats": items})))
    all_chats(engine)
    engine.ingest_messages("111@c.us", [msg()])
    engine.ingest_messages("222@lid", [msg("222@lid", "two")])
    with pytest.raises(RuntimeError):
        engine.analyze()
    assert engine.state()["stats"]["messages_pending"] == 2
    assert engine.state()["tasks"] == [] and engine.state()["summaries"] == []


def test_transient_disconnect_debounced_and_stale_alert_resolves(tmp_path):
    clock = Time()
    statuses = iter(["WORKING", "FAILED", "WORKING", "FAILED", "FAILED", "WORKING"])
    def handler(request):
        if request.url.path == "/api/sessions/default":
            return httpx.Response(200, json={"status": next(statuses)})
        return httpx.Response(200, json=[])
    engine = create(tmp_path, handler, clock)
    engine.connect()
    engine.tick()
    assert not any(n["id"].startswith("connection:") for n in engine.state()["notifications"])
    clock.now += timedelta(seconds=60)
    engine.tick()
    clock.now += timedelta(seconds=60)
    engine.tick()
    clock.now += timedelta(seconds=60)
    engine.tick()
    assert any(n["status"] == "pending" for n in engine.state()["notifications"] if n["id"].startswith("connection:"))
    clock.now += timedelta(seconds=60)
    engine.tick()
    notices = [n for n in engine.state()["notifications"] if n["id"].startswith("connection:")]
    assert notices and all(n["status"] == "resolved" and "recovered" in n["body"].lower() for n in notices)


def test_metadata_only_chat_list_never_caches_content_and_fails_closed(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=[{"id": "111@c.us", "name": "Sam", "type": "direct", "isGroup": False, "unreadCount": 2}])
        return httpx.Response(200, json=[{"id": "111@c.us", "name": "Sam", "type": "direct", "lastMessage": {"body": "PRIVATE-CONTENT-MARKER"}}])
    engine = create(tmp_path, handler)
    assert engine.list_chats() == [{"id": "111@c.us", "name": "Sam", "type": "private"}]
    assert calls[0].url.params["metadataOnly"] == "true"
    with pytest.raises(RuntimeError, match="Chat-list extension unavailable"):
        engine.list_chats()
    engine.close()
    assert b"PRIVATE-CONTENT-MARKER" not in (tmp_path / "assistant.sqlite3").read_bytes()


def test_explicit_pause_cannot_be_silently_undone_by_legacy_selection(tmp_path):
    engine = create(tmp_path)
    engine.update_settings({"selected_groups": [{"id": "work@g.us", "name": "Work"}]})
    engine.update_settings({"processing_consent": False})
    engine.close()
    engine = create(tmp_path)
    engine.update_settings({"selected_groups": [{"id": "work@g.us", "name": "Work"}]})
    assert engine.settings()["processing_consent"] is False
    assert engine.ingest_messages("work@g.us", [msg("work@g.us")]) == 0


def test_recovery_round_robin_is_bounded_and_permission_time_used(tmp_path):
    clock = Time()
    requests = []
    chats = [{"id": f"{n:03}@c.us", "name": str(n), "type": "private"} for n in range(1, 13)]
    def handler(request):
        requests.append(request)
        if request.url.path == "/api/sessions/default":
            return httpx.Response(200, json={"status": "WORKING"})
        if request.url.path == "/api/default/chats":
            return httpx.Response(200, json=chats)
        return httpx.Response(200, json=[])
    engine = create(tmp_path, handler, clock)
    all_chats(engine)
    engine.tick()
    history = [r for r in requests if "/messages" in r.url.path]
    assert len(history) == 10
    assert all(int(r.url.params["filter.timestamp.gte"]) == 1792483200 for r in history)
    clock.now += timedelta(seconds=60)
    engine.tick()
    history = [r for r in requests if "/messages" in r.url.path]
    assert len(history) == 20 and len({r.url.path for r in history}) == 12


def test_allmode_batch_limit_and_budget_survive_restart(tmp_path):
    requests = []
    def handler(request):
        supplied = json.loads(json.loads(request.content)["input"][1]["content"])
        requests.append(supplied)
        return httpx.Response(200, json=api({"chats": [{"chat_id": c["chat_id"], **single(c["messages"][0]["id"])} for c in supplied["chats"]]}))
    engine = create(tmp_path, handler)
    engine.update_settings({"max_calls_per_day": 1})
    all_chats(engine)
    for n in range(1, 7):
        engine.ingest_messages(f"{n}@c.us", [msg(f"{n}@c.us", f"m{n}")])
    assert engine.analyze()["processed"] == 5
    assert len(requests) == 1 and len(requests[0]["chats"]) == 5
    engine.close()
    engine = create(tmp_path, handler)
    with pytest.raises(RuntimeError, match="Daily AI call limit"):
        engine.analyze()
    assert engine.state()["stats"]["messages_pending"] == 1


def test_restoring_excluded_chat_requires_new_grant_and_skips_excluded_period(tmp_path):
    clock = Time()
    engine = create(tmp_path, clock=clock)
    all_chats(engine)
    engine.ingest_messages("111@c.us", [msg()])
    engine.update_settings({"excluded_chat_ids": ["111@c.us"]})
    clock.now += timedelta(hours=2)
    with pytest.raises(ValueError):
        engine.update_settings({"excluded_chat_ids": []})
    engine.update_settings({"excluded_chat_ids": [], "processing_consent": True})
    assert engine.ingest_messages("111@c.us", [msg(mid="during-exclusion", timestamp=1792486800)]) == 0
    assert engine.ingest_messages("111@c.us", [msg(mid="after-grant", timestamp=1792490400)]) == 1


@pytest.mark.parametrize("action", ["pause", "exclude"])
@pytest.mark.parametrize("delivery", ["sent", "failed"])
def test_scope_reduction_purges_digest_copies_in_every_delivery_state(tmp_path, action, delivery):
    marker = "SYNTHETIC-PRIVATE-SUMMARY-MARKER"
    result = single()
    result["summary"] = marker
    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json=api(result))
        if request.url.host == "api.pushover.net":
            return httpx.Response(200 if delivery == "sent" else 400, json={"status": 1 if delivery == "sent" else 0})
        return httpx.Response(200, json={"status": "STOPPED"})
    engine = create(tmp_path, handler)
    engine.update_settings({"selected_chats": [{"id": "111@c.us", "name": "Sam", "type": "private"}], "processing_consent": True, "pushover_token": "token", "pushover_user": "user"})
    engine.ingest_messages("111@c.us", [msg()])
    engine.analyze()
    engine.tick()
    notices = [n for n in engine.state()["notifications"] if n["id"].startswith("digest:")]
    assert len(notices) == 1 and notices[0]["status"] == delivery and marker in notices[0]["body"]
    engine.update_settings({"processing_consent": False} if action == "pause" else {"excluded_chat_ids": ["111@c.us"]})
    state = engine.state()
    assert state["summaries"] == []
    assert marker not in json.dumps(state)
    assert state["tasks"][0]["title"] == "Send invoice"


@pytest.mark.parametrize("alias", ["12125550101@s.whatsapp.net", "12125550101:4@s.whatsapp.net", "12125550101:4@c.us"])
def test_phone_aliases_cannot_bypass_allmode_exclusion(tmp_path, alias):
    engine = create(tmp_path)
    all_chats(engine)
    engine.update_settings({"excluded_chat_ids": ["12125550101@c.us"]})
    assert engine.ingest_event({"event": "message.any", "payload": msg(alias)}) == 0
    assert engine.state()["stats"]["messages_pending"] == 0


def test_selected_phone_aliases_share_scope_without_mapping_unrelated_lids(tmp_path):
    engine = create(tmp_path)
    engine.update_settings({"selected_chats": [{"id": "12125550101:2@s.whatsapp.net", "name": "Sam", "type": "private"}], "processing_consent": True})
    assert engine.settings()["selected_chats"][0]["id"] == "12125550101@c.us"
    assert engine.ingest_messages("12125550101@c.us", [msg("12125550101@c.us")]) == 1
    assert engine.ingest_messages("12125550101@lid", [msg("12125550101@lid", "unrelated")]) == 0


@pytest.mark.parametrize("pn,accepted", [(None, 0), ("12125550101@c.us", 0), ("999@s.whatsapp.net", 1)])
def test_unknown_lid_exclusion_permission_requires_verified_identity_metadata(tmp_path, pn, accepted):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"lid": "777@lid", "pn": pn})
    engine = create(tmp_path, handler)
    all_chats(engine)
    engine.update_settings({"excluded_chat_ids": ["12125550101@c.us"]})
    assert engine.ingest_event({"event": "message.any", "payload": msg("777:2@lid")}) == accepted
    assert len(requests) == 1 and requests[0].url.path == "/api/default/lids/777@lid"
    assert requests[0].method == "GET" and not requests[0].content
    assert not any("messages" in request.url.path for request in requests)
    if accepted:
        assert engine.state()["stats"]["monitored_chats"] == 1
        engine.close()
        engine = create(tmp_path, lambda r: pytest.fail("persisted verified mapping should resolve without network"))
        assert engine.ingest_messages("777@lid", [msg("777@lid", "second")]) == 1
    else:
        assert engine.state()["stats"]["messages_pending"] == 0


def test_aliases_in_persisted_settings_catalog_permission_times_and_tasks_migrate(tmp_path):
    clock = Time()
    engine = create(tmp_path, lambda r: httpx.Response(200, json=api(single())), clock)
    engine.update_settings({"selected_chats": [{"id": "111@c.us", "name": "Sam", "type": "private"}], "processing_consent": True})
    engine.ingest_messages("111@c.us", [msg()])
    engine.analyze()
    engine.close()
    db = sqlite3.connect(tmp_path / "assistant.sqlite3")
    settings = json.loads(db.execute("SELECT value FROM kv WHERE key='settings'").fetchone()[0])
    settings["selected_chats"][0]["id"] = "111:2@s.whatsapp.net"
    db.execute("UPDATE kv SET value=? WHERE key='settings'", (json.dumps(settings),))
    db.execute("UPDATE kv SET value=? WHERE key='chat_catalog'", (json.dumps({"111@s.whatsapp.net": {"id": "111@s.whatsapp.net", "name": "Sam", "type": "private"}}),))
    db.execute("UPDATE kv SET value=? WHERE key='scope_since'", (json.dumps({"111@c.us": "2026-10-20T08:00:00+00:00", "111@s.whatsapp.net": "2026-10-20T09:00:00+00:00"}),))
    for table in ("messages", "summaries", "tasks"):
        db.execute("UPDATE " + table + " SET group_id='111@s.whatsapp.net'")
    db.commit()
    db.close()
    clock.now += timedelta(hours=2)
    engine = create(tmp_path, clock=clock)
    state = engine.state()
    assert state["settings"]["selected_chats"][0]["id"] == "111@c.us"
    assert state["tasks"][0]["chat_id"] == "111@c.us" and state["tasks"][0]["evidence"]
    assert state["summaries"][0]["chat_id"] == "111@c.us"
    assert engine.ingest_messages("111@c.us", [msg(mid="too-old", timestamp=1792485000)]) == 0
    assert engine.ingest_messages("111@s.whatsapp.net", [msg(mid="permitted", timestamp=1792490400)]) == 1


@pytest.mark.parametrize("invalid", ["0@c.us", "0@s.whatsapp.net", "0@lid", "0:2@s.whatsapp.net"])
def test_zero_private_ids_are_not_normal_chats(tmp_path, invalid):
    engine = create(tmp_path)
    all_chats(engine)
    assert engine.ingest_messages(invalid, [msg(invalid)]) == 0


@pytest.mark.parametrize("pn,accepted", [(None, 0), ("12125550101@s.whatsapp.net", 0), ("888@c.us", 1)])
def test_excluded_lid_cannot_be_bypassed_by_phone_alias(tmp_path, pn, accepted):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"lid": "999@lid", "pn": pn})
    engine = create(tmp_path, handler)
    all_chats(engine)
    engine.update_settings({"excluded_chat_ids": ["999@lid"]})
    assert engine.ingest_messages("12125550101@c.us", [msg("12125550101@c.us")]) == accepted
    assert len(requests) == 1 and requests[0].url.path == "/api/default/lids/999@lid"
    assert not requests[0].content
    if pn is None:
        # Permission remains conservative even on a second different private ID.
        assert engine.ingest_messages("777@c.us", [msg("777@c.us", "uncertain")]) == 0
        assert len(requests) == 1  # failed metadata is throttled for 60 seconds
        assert engine.ingest_messages("work@g.us", [msg("work@g.us", "group")]) == 1


def test_verified_mapping_purges_pending_task_even_after_source_retention(tmp_path):
    clock = Time()
    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json=api(single()))
        if "/lids/" in request.url.path:
            return httpx.Response(200, json={"lid": "777@lid", "pn": "12125550101@c.us"})
        return httpx.Response(200, json={"status": "STOPPED"})
    engine = create(tmp_path, handler, clock)
    all_chats(engine)
    engine.ingest_messages("777@lid", [msg("777@lid")])
    engine.analyze()
    task = engine.state()["tasks"][0]
    engine.task_update(task["id"], {"due_at": "2026-10-20T12:00:00+04:00", "needs_review": False})
    engine.tick()  # no Pushover credentials: queued reminder remains local
    engine.db.execute("DELETE FROM messages")
    engine.db.execute("DELETE FROM summaries")
    engine.db.commit()
    # Simulate an older saved policy to exercise the mapping migration independently
    # of the normal settings purge and without inventing message content.
    engine._config["excluded_chat_ids"] = ["12125550101@c.us"]
    assert engine.ingest_messages("777@lid", [msg("777@lid", "blocked")]) == 0
    assert not any(n["id"].startswith("task:" + task["id"]) for n in engine.state()["notifications"])


def test_delivery_revalidates_stale_task_and_digest_permissions(tmp_path):
    clock = Time()
    clock.now = datetime(2026, 10, 20, 18, 30, tzinfo=timezone.utc)
    pushes = []
    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json=api(single()))
        if request.url.host == "api.pushover.net":
            pushes.append(request)
            return httpx.Response(200, json={"status": 1})
        return httpx.Response(200, json={"status": "STOPPED"})
    engine = create(tmp_path, handler, clock)
    all_chats(engine)
    engine.update_settings({"pushover_token": "token", "pushover_user": "user"})
    engine.ingest_messages("111@c.us", [msg(timestamp=clock.now.timestamp())])
    engine.analyze()
    task = engine.state()["tasks"][0]
    engine.task_update(task["id"], {"due_at": "2026-10-20T23:00:00+04:00", "needs_review": False})
    engine.tick()
    # Simulate a stale outbox from a past build: delivery must recheck scope even if
    # an earlier mutator omitted cleanup.
    engine._config["excluded_chat_ids"] = ["111@c.us"]
    clock.now = datetime(2026, 10, 21, 4, 0, tzinfo=timezone.utc)
    engine.tick()
    assert pushes == []
