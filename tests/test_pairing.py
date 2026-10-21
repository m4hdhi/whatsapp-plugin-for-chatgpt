import httpx
import pytest

from app.core import Engine


def test_failed_session_restarts_instead_of_idempotent_start(tmp_path):
    paths = []

    def handler(request):
        paths.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"status": "FAILED"})
        if request.url.path.endswith("/restart"):
            return httpx.Response(201, json={"status": "STARTING"})
        return httpx.Response(201, json={"status": "FAILED"})

    engine = Engine(tmp_path, transport=httpx.MockTransport(handler))
    result = engine.connect()
    assert result["status"] == "STARTING"
    assert paths == [("GET", "/api/sessions/default"), ("POST", "/api/sessions/default/restart")]
    engine.close()


@pytest.mark.parametrize("status", ["STARTING", "SCAN_QR_CODE", "WORKING", "FAILED", "STOPPED"])
def test_qr_lifecycle_status_is_explained_without_generic_service_error(tmp_path, status):
    engine = Engine(tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(422, json={
        "error": "Session status does not support this operation", "session": "default", "status": status,
        "expected": ["SCAN_QR_CODE"],
    })))
    result = engine.qr()
    assert result["ready"] is False
    assert result["status"] == status
    assert result["data"] == ""
    assert result["message"]
    assert engine.state()["connection"]["status"] == status
    engine.close()


def test_valid_qr_clears_stale_connection_warning(tmp_path):
    engine = Engine(tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
        "mimetype": "image/png", "data": "aGVsbG8=",
    })))
    engine._error("WhatsApp connection check failed. Check WhatsApp on Overview; messages can be missed while disconnected.")
    engine._error("OpenAI rate limit or API credit limit reached. Messages remain pending.")
    result = engine.qr()
    assert result["ready"] is True
    assert result["status"] == "SCAN_QR_CODE"
    assert engine.state()["connection"]["error"] is None
    assert not any(error.startswith("WhatsApp connection check failed.") for error in engine.state()["errors"])
    assert any(error.startswith("OpenAI rate limit") for error in engine.state()["errors"])
    engine.close()
