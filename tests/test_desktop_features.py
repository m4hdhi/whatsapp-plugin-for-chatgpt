from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import Engine
from app.server import create_app
from app.integrations import shared_brief
from native.mcp_link import dispatch
from native.plugin_install import register_plugin


def test_desktop_notifications_without_pushover_and_persisted_partial_delivery(tmp_path):
    now = [datetime(2026, 10, 20, 8, tzinfo=timezone.utc)]
    local, remote = [], []
    def notify(title, body):
        local.append((title, body))
    def transport(request):
        remote.append(request)
        return httpx.Response(500 if len(remote) == 1 else 200, json={"status": 1})
    engine = Engine(tmp_path, clock=lambda: now[0], desktop_notify=notify, transport=httpx.MockTransport(transport))
    engine.update_settings({"desktop_notifications": True})
    assert engine.test_notification()["status"] == "sent"
    assert len(local) == 1 and remote == []
    engine.update_settings({"pushover_token": "synthetic-token", "pushover_user": "synthetic-user"})
    with pytest.raises(RuntimeError):
        engine.test_notification()
    assert len(local) == 2 and len(remote) == 1
    engine.close()
    engine = Engine(tmp_path, clock=lambda: now[0], desktop_notify=notify, transport=httpx.MockTransport(transport))
    now[0] += timedelta(minutes=3)
    engine._deliver()
    assert len(local) == 2 and len(remote) == 2  # successful Windows delivery is not replayed
    assert all(n["status"] == "sent" for n in engine.state()["notifications"])
    engine.close()


def test_demo_does_not_contact_push_provider_even_if_credentials_are_entered(tmp_path):
    requests = []
    def remote(request):
        requests.append(request)
        raise AssertionError("A demo must never use external services")
    engine = Engine(tmp_path, demo=True, transport=httpx.MockTransport(remote))
    engine.update_settings({"pushover_token": "synthetic-token", "pushover_user": "synthetic-user"})
    assert engine.test_notification()["status"] == "sent" and requests == []
    engine.close()


def test_readonly_chatgpt_key_is_separate_and_permissions_revoke_immediately(tmp_path):
    engine = Engine(tmp_path, demo=True)
    engine.update_settings({"openai_api_key": "synthetic-provider-secret"})
    admin, read, hook = "a" * 64, "r" * 64, "h" * 64
    registered = []
    app = create_app(engine, admin_token=admin, webhook_secret=hook, chatgpt_token=read, run_scheduler=False,
                     register_chatgpt=lambda: registered.append(True) or {"status": "available"})
    with TestClient(app, base_url="http://127.0.0.1") as client:
        ro = {"Authorization": "Bearer " + read}
        owner = {"Authorization": "Bearer " + admin}
        assert client.get("/api/chatgpt/brief", headers=ro).status_code == 403
        assert client.post("/api/chatgpt/register", headers=owner).status_code == 403
        assert registered == []
        for endpoint in ("/api/state", "/api/chats", "/api/export"):
            assert client.get(endpoint, headers=ro).status_code == 401
        assert client.post("/api/settings", headers=ro, json={"processing_consent": True}).status_code == 401
        assert client.post("/api/chatgpt/register", headers=ro).status_code == 401
        assert client.post("/api/settings", headers=owner, json={"chatgpt_enabled": True}).status_code == 200
        brief = client.get("/api/chatgpt/brief", headers=ro)
        assert brief.status_code == 200 and brief.json()["tasks"]
        assert "synthetic-provider-secret" not in brief.text
        assert all("evidence" not in task and "source_ids" not in task for task in brief.json()["tasks"])
        assert set(brief.json()) == {"data_notice", "monitoring_allowed", "timezone", "summaries", "tasks"}
        assert "UNTRUSTED" in brief.json()["data_notice"]
        assert client.post("/api/chatgpt/register", headers=owner).json()["status"] == "available"
        assert registered == [True]
        client.post("/api/settings", headers=owner, json={"processing_consent": False})
        paused = client.get("/api/chatgpt/brief", headers=ro).json()
        assert paused["tasks"] == [] and paused["summaries"] == []
        client.post("/api/settings", headers=owner, json={"chatgpt_enabled": False})
        assert client.get("/api/chatgpt/status", headers=ro).status_code == 403
    engine.close()


def test_plugin_registration_preserves_existing_personal_plugins_and_requires_owned_target(tmp_path):
    home, source = tmp_path / "home", tmp_path / "plugin"
    (source / "bin").mkdir(parents=True)
    (source / "bin" / "GroupBriefLink.exe").write_bytes(b"synthetic-build-fixture")
    (source / "plugin.json").write_text('{}')
    catalog = home / ".agents" / "plugins" / "marketplace.json"
    catalog.parent.mkdir(parents=True)
    other = {"name": "existing-user-plugin", "source": "./existing"}
    catalog.write_text(json.dumps({"name": "existing-marketplace", "plugins": [other]}))
    assert register_plugin(source, home)["status"] == "available"
    result = json.loads(catalog.read_text())
    assert result["name"] == "existing-marketplace" and result["plugins"][0] == other
    assert result["plugins"][1]["policy"]["installation"] == "AVAILABLE"
    assert not (home / ".codex" / "config.toml").exists()
    register_plugin(source, home)
    assert len(json.loads(catalog.read_text())["plugins"]) == 2
    register_plugin(home / '.codex/plugins/groupbrief', home)
    assert len(json.loads(catalog.read_text())["plugins"]) == 2
    (home / ".codex" / "plugins" / "groupbrief" / ".groupbrief-owned").unlink()
    before = catalog.read_bytes()
    with pytest.raises(RuntimeError):
        register_plugin(source, home)
    assert catalog.read_bytes() == before


def test_mcp_protocol_reads_briefs_and_exposes_only_explicit_local_setup():
    tools = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    assert {tool['name'] for tool in tools} == {'read_whatsapp_messages', 'get_whatsapp_brief', 'list_whatsapp_tasks', 'groupbrief_status', 'open_whatsapp_setup'}
    assert all(t['annotations']['readOnlyHint'] for t in tools if t['name'] != 'open_whatsapp_setup')
    assert next(t for t in tools if t['name'] == 'open_whatsapp_setup')['annotations']['readOnlyHint'] is False
    assert dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    response = dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_whatsapp_tasks", "arguments": {}}},
                        lambda _: {"data_notice": "untrusted", "timezone": "UTC", "tasks": [{"title": "Synthetic task"}], "summaries": [{"summary": "Not needed in task tool"}]})
    value = json.loads(response["result"]["content"][0]["text"])
    assert value["tasks"] and "summaries" not in value
    invalid = dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "send_message", "arguments": {}}})
    assert invalid["error"]["code"] == -32602


@pytest.mark.parametrize('missing', ['GroupBrief.exe', 'runtime/node.exe',
                                    'runtime/chromium/chrome.exe', 'bridge/bridge.cjs',
                                    'bridge/node_modules/whatsapp-web.js/package.json',
                                    '_internal/static/app.js'])
def test_incomplete_portable_helper_does_not_register_or_overwrite_plugin(tmp_path, missing):
    source, home = tmp_path / 'source', tmp_path / 'home'
    files = ['bin/GroupBriefLink.exe', 'helper/GroupBrief.exe', 'helper/runtime/node.exe',
             'helper/runtime/chromium/chrome.exe', 'helper/bridge/bridge.cjs',
             'helper/bridge/node_modules/whatsapp-web.js/package.json', 'helper/_internal/static/app.js']
    for name in files:
        file = source / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('synthetic fixture')
    (source / 'helper' / missing).unlink()
    with pytest.raises(RuntimeError, match='complete'):
        register_plugin(source, home)
    assert not (home / '.codex/plugins/groupbrief').exists()
    assert not (home / '.agents/plugins/marketplace.json').exists()


@pytest.mark.parametrize('status', [401, 403])
def test_mcp_distinguishes_helper_authentication_from_message_permission(status):
    from urllib.error import HTTPError

    def rejected(_):
        raise HTTPError('http://127.0.0.1:8767/api/chatgpt/messages', status,
                        'synthetic rejection', {}, None)

    response = dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                         'params': {'name': 'read_whatsapp_messages', 'arguments': {'hours': 1}}}, rejected)
    assert response['result']['isError'] is True
    text = response['result']['content'][0]['text']
    if status == 401:
        assert 'authentication' in text.lower()
        assert 'older' in text.lower()
        assert 'sharing is disabled' not in text.lower()
    else:
        assert 'sharing is disabled' in text.lower()


def test_plugin_starts_bundled_helper_without_shell_and_reuses_existing_instance(tmp_path, monkeypatch):
    from native import mcp_link
    launched = []
    checks = iter([False, False, True])
    (tmp_path / 'helper').mkdir()
    executable = tmp_path / 'helper/GroupBrief.exe'
    executable.write_bytes(b'synthetic-runtime')
    monkeypatch.setattr(mcp_link, 'healthy', lambda _: next(checks))
    monkeypatch.setattr(mcp_link.subprocess, 'Popen', lambda args, **kwargs: launched.append((args, kwargs)))
    monkeypatch.setattr(mcp_link.time, 'sleep', lambda _: None)
    mcp_link.ensure_running(tmp_path)
    assert launched[0][0] == [str(executable), '--background']
    assert 'shell' not in launched[0][1] and len(launched) == 1
    monkeypatch.setattr(mcp_link, 'healthy', lambda _: True)
    mcp_link.ensure_running(tmp_path)
    assert len(launched) == 1


def test_plugin_setup_returns_credit_without_exposing_admin_credentials(monkeypatch):
    from native import mcp_link
    import urllib.error
    calls = []
    monkeypatch.setattr(mcp_link, 'ensure_running', lambda: None)
    monkeypatch.setattr(mcp_link, 'runtime_config', lambda: {'url': 'http://127.0.0.1:8767'})
    monkeypatch.setattr(Path, 'read_text', lambda self, **kwargs: json.dumps({'admin_token': 'a' * 64}))
    monkeypatch.setattr(mcp_link.webbrowser, 'open', lambda url: calls.append(url) or True)
    result = mcp_link.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'open_whatsapp_setup'}},
                               lambda _: pytest.fail('Setup must not read chat content'))
    assert result['result']['isError'] is False
    assert 'a' * 64 not in json.dumps(result)
    assert calls == ['http://127.0.0.1:8767/#token=' + 'a' * 64]
    assert 'https://www.linkedin.com/in/m4hdhi/' in json.dumps(result)


def test_shared_brief_applies_output_limits_after_permission_filtering(tmp_path):
    clock = lambda: datetime(2026, 10, 20, 8, tzinfo=timezone.utc)
    engine = Engine(tmp_path, demo=True, clock=clock)
    engine.update_settings({"chatgpt_enabled": True})
    for index in range(301):
        engine.db.execute("INSERT INTO summaries VALUES (?,?,?,?,?)", ("hidden-summary-" + str(index), "hidden@g.us", "Excluded summary", "2026-10-20T09:00:00+00:00", "[]"))
        engine.db.execute("INSERT INTO tasks(id,group_id,title,normalized,due_at,needs_review,status,confidence,created_at,source_ids,reminder_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          ("hidden-task-" + str(index), "hidden@g.us", "Excluded task", "excluded", "2026-10-20T09:00:00+00:00", 0, "open", .99, "2026-10-20T08:00:00+00:00", "[]", None))
    engine.db.commit()
    result = shared_brief(engine)
    assert len(result["summaries"]) == 1 and len(result["tasks"]) == 1
    assert "Excluded" not in json.dumps(result)
    engine.close()
