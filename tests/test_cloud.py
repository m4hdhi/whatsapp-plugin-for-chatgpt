"""Hosted account, consent and remote MCP boundaries with synthetic data only."""
import copy
from datetime import datetime, timezone
import hashlib
import hmac
import html
import json
import re
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import httpx
import pytest

from app.core import Engine
from cloud.auth import challenge, password_hash
from cloud.server import create_app, validate_config
from cloud.manage import compose

BASE = "https://wa.example.test"
CLIENT = "synthetic-client-123"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
PASSWORD = "synthetic account password only"


@pytest.fixture(scope="module")
def configuration():
    encoded = password_hash(PASSWORD)
    return {"public_url": BASE, "oauth_clients": {CLIENT: {"redirect_uris": [REDIRECT]}},
            "users": {uid: {"password_hash": encoded, "bridge_key": char * 64,
                             "hook_secret": char * 64, "bridge_url": f"http://bridge-{uid}:3000"}
                      for uid, char in (("alice", "a"), ("bobby", "b"))}}


@pytest.fixture
def hosted(tmp_path, configuration):
    calls = []
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    ticks = [now.timestamp()]
    def factory(**kwargs):
        def remote(request):
            calls.append(request)
            return httpx.Response(200, json={"status": "WORKING"})
        return Engine(**kwargs, clock=lambda: now, transport=httpx.MockTransport(remote))
    app = create_app(copy.deepcopy(configuration), tmp_path, engine_factory=factory,
                     run_scheduler=False, clock=lambda: ticks[0])
    with TestClient(app, base_url=BASE) as client:
        yield client, app, calls, now, ticks


def hidden(markup, name):
    return html.unescape(re.search(r'name="' + name + r'" (?:content|value)="([^"]*)"', markup).group(1))


def login(client, uid="alice"):
    page = client.get("/login")
    result = client.post("/login", data={"username": uid, "password": PASSWORD, "csrf": hidden(page.text, "csrf"), "next": "/"},
                         headers={"Origin": BASE}, follow_redirects=False)
    assert result.status_code == 303
    return hidden(client.get("/").text, "csrf-token")


def authorization(client, uid="alice", **overrides):
    login(client, uid)
    verifier = "v" * 64
    params = {"client_id": CLIENT, "redirect_uri": REDIRECT, "response_type": "code", "scope": "whatsapp:read",
              "state": "opaque-state", "resource": BASE + "/mcp", "code_challenge_method": "S256", "code_challenge": challenge(verifier)}
    params.update(overrides)
    response = client.get("/oauth/authorize", params=params)
    assert response.status_code == 200
    consent = client.post("/oauth/authorize", data={"pending": hidden(response.text, "pending"), "csrf": hidden(response.text, "csrf"), "decision": "allow"},
                          headers={"Origin": BASE}, follow_redirects=False)
    assert consent.status_code == 303
    result = parse_qs(urlsplit(consent.headers["location"]).query)
    assert result["iss"] == [BASE] and result["state"] == ["opaque-state"]
    return {"grant_type": "authorization_code", "client_id": CLIENT, "code": result["code"][0],
            "redirect_uri": REDIRECT, "code_verifier": verifier, "resource": BASE + "/mcp"}


def token(client, uid="alice"):
    result = client.post("/oauth/token", data=authorization(client, uid))
    assert result.status_code == 200
    return result.json()


def rpc(client, access, name="read_whatsapp_messages", arguments=None, method="tools/call"):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method,
                                    "params": {"name": name, "arguments": arguments or {}}},
                       headers={"Authorization": "Bearer " + access})


def permit(app, uid="alice"):
    app.state.engines[uid].update_settings({"processing_consent": True, "monitoring_mode": "all", "chatgpt_messages_enabled": True})


def ingest(client, now, uid="alice", chat="99@c.us", body="Mahdhi submit the project in 5 min", mid="one"):
    payload = json.dumps({"event": "message.any", "payload": {"id": mid, "from": chat, "body": body,
                         "timestamp": int(now.timestamp()), "fromMe": False}}).encode()
    key = ("a" if uid == "alice" else "b") * 64
    signature = hmac.new(key.encode(), payload, hashlib.sha512).hexdigest()
    return client.post("/hooks/" + uid, content=payload, headers={"X-Webhook-Hmac": signature})


def test_browser_session_requires_auth_csrf_and_secure_cookie(hosted):
    client, app, calls, now, ticks = hosted
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/api/state").status_code == 401
    csrf = login(client)
    assert 'data-hosted="true"' in client.get("/").text
    assert client.get("/api/state").json()["configured"]["hosted"] is True
    assert client.post("/api/settings", json={"processing_consent": True}).status_code == 403
    assert client.post("/api/settings", json={"processing_consent": True}, headers={"Origin": "https://evil.test", "X-CSRF-Token": csrf}).status_code == 403
    assert client.post("/api/settings", json={"processing_consent": True}, headers={"Origin": BASE, "X-CSRF-Token": csrf}).status_code == 200
    assert client.post("/api/chatgpt/register", headers={"Origin": BASE, "X-CSRF-Token": csrf}).status_code == 404
    assert client.get("/api/chatgpt/messages").status_code == 404
    assert client.get("/health", headers={"Host": "evil.test"}).status_code == 400
    assert client.get("/health", headers={"Host": "gateway:8000"}).status_code == 400
    assert client.get("/").headers["cache-control"] == "no-store"
    cookies = list(client.cookies.jar)
    assert any(c.name == "__Host-wa_session" and c.secure and c._rest.get("HttpOnly") is None for c in cookies)
    ticks[0] += 12 * 3600 + 1
    assert client.get("/api/state").status_code == 401


def test_mcp_auth_discovery_scoped_tools_and_no_desktop_launch(hosted):
    client, app, calls, now, ticks = hosted
    response = client.post("/mcp", json={})
    assert response.status_code == 401 and "resource_metadata" in response.headers["www-authenticate"]
    assert client.get("/.well-known/oauth-protected-resource").json()["resource"] == BASE + "/mcp"
    metadata = client.get("/.well-known/oauth-authorization-server").json()
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert metadata["authorization_response_iss_parameter_supported"] is True
    access = token(client)["access_token"]
    init = rpc(client, access, method="initialize").json()["result"]
    assert init["protocolVersion"] == "2025-06-18" and "UNTRUSTED" in init["instructions"]
    tools = rpc(client, access, method="tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"read_whatsapp_messages", "get_whatsapp_brief", "list_whatsapp_tasks", "groupbrief_status", "get_whatsapp_setup"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    assert rpc(client, access, "open_whatsapp_setup").json()["error"]["code"] == -32602
    assert rpc(client, access, arguments={"user": "bobby"}).json()["error"]["code"] == -32602
    assert rpc(client, access, arguments={"limit": True}).json()["error"]["code"] == -32602
    assert BASE in rpc(client, access, "get_whatsapp_setup").text
    assert calls == []


def test_two_users_cannot_read_each_others_chats_and_reads_are_keyless(hosted):
    client, app, calls, now, ticks = hosted
    permit(app, "alice")
    permit(app, "bobby")
    assert ingest(client, now, "alice", body="ALICE confidential project").json()["accepted"] == 1
    assert ingest(client, now, "bobby", body="BOBBY confidential invoice").json()["accepted"] == 1
    alice = token(client, "alice")["access_token"]
    bobby = token(client, "bobby")["access_token"]
    # Browser is now Bobby, but Alice's OAuth token still selects only Alice.
    first = rpc(client, alice).text
    second = rpc(client, bobby).text
    assert "ALICE confidential" in first and "BOBBY confidential" not in first
    assert "BOBBY confidential" in second and "ALICE confidential" not in second
    assert calls == []
    assert app.state.engines["alice"].state()["stats"]["messages_pending"] == 1
    assert app.state.engines["alice"].state()["configured"]["openai"] is False
    # OAuth grants are not dashboard credentials.
    client.cookies.clear()
    assert client.get("/api/state", headers={"Authorization": "Bearer " + alice}).status_code == 401


def test_permission_revocation_and_exclusions_apply_to_existing_tokens(hosted):
    client, app, calls, now, ticks = hosted
    access = token(client)["access_token"]
    assert rpc(client, access).json()["result"]["isError"] is True
    permit(app)
    ingest(client, now, body="allowed request")
    ingest(client, now, chat="88@g.us", body="excluded group", mid="two")
    app.state.engines["alice"].update_settings({"excluded_chat_ids": ["88@g.us"]})
    response = rpc(client, access)
    assert "allowed request" in response.text and "excluded group" not in response.text
    app.state.engines["alice"].update_settings({"chatgpt_messages_enabled": False})
    assert rpc(client, access).json()["result"]["isError"] is True
    assert "allowed request" not in rpc(client, access).text


def test_oauth_code_pkce_redirect_resource_and_replay(hosted):
    client, app, calls, now, ticks = hosted
    data = authorization(client)
    assert client.post("/oauth/token", data={**data, "code_verifier": "x" * 64}).status_code == 400
    assert client.post("/oauth/token", data=data).status_code == 400
    data = authorization(client)
    assert client.post("/oauth/token", data={**data, "redirect_uri": "https://evil.test/"}).status_code == 400
    data = authorization(client)
    assert client.post("/oauth/token", data={**data, "resource": "https://other.test/mcp"}).status_code == 400
    success = client.post("/oauth/token", data=data)
    assert success.status_code == 200
    assert client.post("/oauth/token", data=data).status_code == 400
    params = {"client_id": CLIENT, "redirect_uri": "https://evil.test/"}
    assert client.get("/oauth/authorize", params=params).status_code == 400
    ticks[0] += 901
    assert rpc(client, success.json()["access_token"]).status_code == 401


def test_refresh_rotation_replay_and_grant_revocation(hosted):
    client, app, calls, now, ticks = hosted
    credentials = token(client)
    request = {"grant_type": "refresh_token", "refresh_token": credentials["refresh_token"], "client_id": CLIENT, "resource": BASE + "/mcp"}
    refreshed = client.post("/oauth/token", data=request)
    assert refreshed.status_code == 200
    assert rpc(client, refreshed.json()["access_token"], method="ping").status_code == 200
    assert client.post("/oauth/token", data=request).status_code == 400
    assert rpc(client, refreshed.json()["access_token"]).status_code == 401
    credentials = token(client)
    csrf = hidden(client.get("/").text, "csrf-token")
    assert client.post("/api/account/revoke", headers={"Origin": BASE, "X-CSRF-Token": csrf}).status_code == 200
    assert rpc(client, credentials["access_token"]).status_code == 401
    assert client.get("/api/state").status_code == 200


def test_webhook_signature_tenant_binding_and_no_secrets_in_state(hosted):
    client, app, calls, now, ticks = hosted
    permit(app)
    assert client.post("/hooks/alice", json={}).status_code == 401
    assert client.post("/hooks/alice", content=b"{}", headers={"X-Webhook-Hmac": hmac.new(b"b" * 64, b"{}", hashlib.sha512).hexdigest()}).status_code == 401
    assert ingest(client, now).status_code == 200
    login(client)
    value = client.get("/api/state").text
    assert "a" * 64 not in value and "password_hash" not in value
    app.state.engines["alice"].update_settings({"openai_api_key": "SYNTHETIC-SECRET-DO-NOT-RETURN"})
    assert "SYNTHETIC-SECRET" not in client.get("/api/state").text


def test_invalid_mcp_and_login_csrf(hosted):
    client, app, calls, now, ticks = hosted
    assert client.post("/login", data={"username": "alice", "password": PASSWORD}).status_code == 403
    access = token(client)["access_token"]
    headers = {"Authorization": "Bearer " + access, "Content-Type": "application/json"}
    assert client.post("/mcp", content="[]", headers=headers).status_code == 400
    assert client.post("/mcp", content="bad-json", headers=headers).status_code == 400
    assert client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers).status_code == 202
    assert client.get("/mcp", headers=headers).status_code == 405
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": True, "method": "ping"}, headers=headers).status_code == 400
    assert client.post("/mcp", json={}, headers={**headers, "MCP-Protocol-Version": "future"}).status_code == 400


def test_config_and_generated_deployment_isolation(configuration, tmp_path):
    config = copy.deepcopy(configuration)
    assert validate_config(config)
    deployment = compose(config, tmp_path)
    assert all("ports" not in value for name, value in deployment["services"].items() if name != "https")
    alice = deployment["services"]["bridge-alice"]
    bobby = deployment["services"]["bridge-bobby"]
    assert set(alice["networks"]).isdisjoint(bobby["networks"])
    assert set(alice["volumes"]).isdisjoint(bobby["volumes"])
    assert alice["cap_drop"] == ["ALL"]
    config["users"]["alice"]["bridge_url"] = "http://169.254.169.254/"
    with pytest.raises(ValueError):
        validate_config(config)
