"""Bounded, private cPanel runtime check. Never scans or prints a pairing QR."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

import httpx
from .auth import password_hash
from .manage import private_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--chrome", required=True)
    args = parser.parse_args()
    parent = args.directory.resolve()
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="cp-", dir=parent))
    key = secrets.token_hex(32)
    private_write(directory / "runtime.json", json.dumps({"python":sys.executable, "node":args.node, "chrome":args.chrome}))
    private_write(directory / "config.json", json.dumps({"public_url":"https://wa.example.test", "users":{
        "probe":{"password_hash":password_hash(secrets.token_urlsafe(32)), "bridge_key":key,
                 "hook_secret":secrets.token_hex(32), "bridge_url":"http://bridge-probe:3000"}}, "oauth_clients":{}}))
    env = {**os.environ, "WA_CPANEL_DIR":str(directory)}
    process = subprocess.Popen([sys.executable, "-m", "cloud.cpanel"], env=env)
    try:
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(directory / "run/gateway.sock")),
                          base_url="http://wa.example.test", timeout=10) as gateway, \
             httpx.Client(transport=httpx.HTTPTransport(uds=str(directory / "run/bridge-probe.sock")),
                          base_url="http://bridge-probe:3000", headers={"X-Api-Key":key}, timeout=10) as bridge:
            deadline = time.monotonic() + 150
            health = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Private runtime exited before becoming ready")
                try:
                    health = gateway.get("/health")
                    status = bridge.get("/api/sessions/default").json().get("status")
                    if health.status_code == 200 and status == "SCAN_QR_CODE":
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(2)
            else:
                raise RuntimeError("Gateway/WhatsApp did not become ready within 150 seconds")
            assert gateway.get("/api/state").status_code == 401
            assert gateway.post("/hooks/probe", json={}).status_code == 401
            duplicate = subprocess.run([sys.executable, "-m", "cloud.cpanel"], env=env, timeout=15)
            assert duplicate.returncode == 0 and gateway.get("/health").status_code == 200
            print("PASS: private gateway, authenticated bridge, sandboxed WhatsApp QR readiness, duplicate-runtime guard.", flush=True)
            print("No QR or message was printed. No account was paired.", flush=True)
    finally:
        process.terminate()
        try:
            process.wait(timeout=35)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            # Preserve files if normal cleanup failed, for operator inspection.
            raise RuntimeError("Runtime did not stop cleanly; private probe directory preserved")
        if directory.parent == parent and directory.name.startswith("cp-"):
            shutil.rmtree(directory)


if __name__ == "__main__":
    main()
