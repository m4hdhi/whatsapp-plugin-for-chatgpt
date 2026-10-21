"""Private Unix-socket runtime supervised by the cPanel Passenger entrypoint.

No TCP listener, Docker, root access or sandbox bypass is used in this mode.
The file lock prevents duplicate engines if Passenger creates extra frontends.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess


def main():
    os.umask(0o077)
    directory = Path(os.environ["WA_CPANEL_DIR"]).resolve()
    runtime = json.loads((directory / "runtime.json").read_text())
    config_file = directory / "config.json"
    config = json.loads(config_file.read_text())
    sockets = directory / "run"
    sockets.mkdir(mode=0o700, parents=True, exist_ok=True)
    sockets.chmod(0o700)
    if len(str(sockets / "bridge-")) + 46 >= 104:
        raise ValueError("Choose a shorter private configuration path for Unix sockets.")
    lock = (sockets / "runtime.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # Another Passenger frontend already owns the runtime.
    # Take the lock before loading the application: duplicate frontends must
    # exit quickly even when importing dependencies from a slow shared disk.
    import httpx
    import uvicorn
    from app.core import Engine
    from .server import create_app, validate_config
    validate_config(config)
    for name in ["gateway.sock"] + [f"bridge-{uid}.sock" for uid in config["users"]]:
        target = sockets / name
        if target.is_socket():
            target.unlink()  # Stale sockets only, while holding the exclusive lock.
        elif target.exists():
            raise ValueError("Unexpected file in private socket directory.")

    def factory(**kwargs):
        uid = kwargs["data_dir"].name
        return Engine(**kwargs, transport=httpx.HTTPTransport(uds=str(sockets / f"bridge-{uid}.sock")))

    app = create_app(config, directory / "data", engine_factory=factory)
    root = Path(__file__).resolve().parent.parent
    children = []
    try:
        for uid, user in config["users"].items():
            session = directory / "sessions" / uid
            session.mkdir(mode=0o700, parents=True, exist_ok=True)
            env = {**os.environ, "WA_ACCOUNT": uid, "WAHA_API_KEY": user["bridge_key"],
                   "APP_WEBHOOK_SECRET": user["hook_secret"], "WA_CLOUD_SOCKET_DIR": str(sockets),
                   "WA_SESSION_ROOT": str(session), "WA_CHROME": runtime["chrome"]}
            # Separate process groups allow all of this worker's Chrome children
            # to be cleaned up, without touching other hosted applications.
            child = subprocess.Popen([runtime["node"], str(root / "cloud/bridge.cjs")],
                                     cwd=root, env=env, start_new_session=True)
            children.append(child)
        server = uvicorn.Server(uvicorn.Config(app, uds=str(sockets / "gateway.sock"),
                                              access_log=False, proxy_headers=False, workers=1))

        async def run():
            async def watch():
                while not server.should_exit:
                    if os.getppid() == 1 or any(child.poll() is not None for child in children):
                        server.should_exit = True
                    await asyncio.sleep(2)
            monitor = asyncio.create_task(watch())
            try:
                await server.serve()
            finally:
                server.should_exit = True
                await monitor
        asyncio.run(run())
    finally:
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        lock.close()


if __name__ == "__main__":
    main()
