"""Real Linux supervisor/socket lifecycle; the worker is a synthetic HTTP peer.

This does not test Chromium or WhatsApp. Those require the host probe separately.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx
import pytest

from cloud.auth import password_hash


@pytest.mark.skipif(sys.platform != "linux", reason="cPanel runtime uses Linux Unix sockets and flock")
def test_private_runtime_lock_authentication_and_shutdown():
    with tempfile.TemporaryDirectory(prefix="wa-cp-") as temp:
        directory = Path(temp)
        worker = directory / "fake-node"
        worker.write_text(f"#!{sys.executable}\n" + '''
import http.server, json, os, socketserver
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status":"SCAN_QR_CODE"}).encode()
        self.send_response(200)
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass
path = os.path.join(os.environ["WA_CLOUD_SOCKET_DIR"], "bridge-probe.sock")
with socketserver.UnixStreamServer(path, Handler) as server:
    server.serve_forever()
''')
        worker.chmod(0o700)
        (directory / "runtime.json").write_text(json.dumps({"node":str(worker), "chrome":"/unused-test-chrome"}))
        (directory / "config.json").write_text(json.dumps({"public_url":"https://wa.example.test", "users":{
            "probe":{"password_hash":password_hash("synthetic test password only"),
                     "bridge_key":"a" * 64, "hook_secret":"b" * 64,
                     "bridge_url":"http://bridge-probe:3000"}}, "oauth_clients":{}}))
        env = {**os.environ, "WA_CPANEL_DIR":str(directory)}
        process = subprocess.Popen([sys.executable, "-m", "cloud.cpanel"], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        socket_path = directory / "run/gateway.sock"
        try:
            with httpx.Client(transport=httpx.HTTPTransport(uds=str(socket_path)),
                              base_url="http://wa.example.test", timeout=5) as client:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    assert process.poll() is None
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.1)
                else:
                    pytest.fail("Private gateway did not start")
                assert (directory / "run").stat().st_mode & 0o077 == 0
                assert client.get("/api/state").status_code == 401
                assert client.post("/hooks/probe", json={}).status_code == 401
                duplicate = subprocess.run([sys.executable, "-m", "cloud.cpanel"], env=env, timeout=10)
                assert duplicate.returncode == 0
                assert client.get("/health").status_code == 200
        finally:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                pytest.fail("Supervisor did not stop cleanly")
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(socket_path)), timeout=2) as client:
            with pytest.raises(httpx.TransportError):
                client.get("http://wa.example.test/health")
