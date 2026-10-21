"""Self-contained Windows launcher; all runtimes are inside the installed folder."""
from __future__ import annotations
import argparse
import atexit
import csv
import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
DEFAULT_DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GroupBrief"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        system = Path(os.environ["SystemRoot"]) / "System32"
        result = subprocess.run([str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"], capture_output=True, check=True, creationflags=NO_WINDOW)
        sid = next(csv.reader(result.stdout.decode(errors="replace").splitlines()))[-1]
        if not re.fullmatch(r"S-1-[0-9-]+", sid):
            raise RuntimeError("Windows could not identify the current user.")
        subprocess.run([str(system / "icacls.exe"), str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, creationflags=NO_WINDOW)
    else:
        path.chmod(0o700)


def read_config(directory):
    private_directory(directory)
    config_file = directory / "local-config.json"
    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
        if any(not isinstance(config.get(key), str) or len(config[key]) < 32 for key in ("admin_token", "hook_secret", "bridge_key", "read_token")):
            raise RuntimeError("The private local configuration is invalid. Restore your private backup; do not share its contents.")
        return config
    config = {key: secrets.token_hex(32) for key in ("admin_token", "hook_secret", "bridge_key", "read_token")}
    config["port"] = 8765
    config_file.write_text(json.dumps(config), encoding="utf-8")
    return config


def request_local(url, token, method="GET"):
    request = urllib.request.Request(url, method=method, headers={"Authorization": "Bearer " + token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=3) as response:
        return json.loads(response.read(4096))


def dashboard(directory, config):
    runtime = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"http://127\.0\.0\.1:\d{4,5}", runtime.get("url", "")):
        raise RuntimeError("Invalid local dashboard address.")
    return runtime["url"] + "/#token=" + config["admin_token"]


def bind_dashboard(preferred=8765):
    for port in list(dict.fromkeys([preferred] + list(range(8765, 8800)))):
        if not isinstance(port, int) or not 1024 <= port <= 65535:
            continue
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return sock
        except OSError:
            sock.close()
    raise RuntimeError("No local dashboard port is available between 8765 and 8799.")


class ChildJob:
    """Closing the Windows Job kills only this app's Node/Chromium children."""
    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Counters), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        handle = api.CreateJobObjectW(None, None)
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not handle or not api.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not api.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
            if handle:
                api.CloseHandle(wintypes.HANDLE(handle))
            process.terminate()
            raise RuntimeError("Windows could not isolate the local WhatsApp runtime.")
        self.handle = handle

    def close(self):
        if self.handle:
            ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(self.handle))
            self.handle = None


class BridgeProcess:
    def __init__(self, directory, config, app_port):
        self.directory, self.config = directory, config
        temporary = socket.socket()
        temporary.bind(("127.0.0.1", 0))
        self.port = temporary.getsockname()[1]
        temporary.close()
        self.environment = {**os.environ, "GROUPBRIEF_DATA_DIR": str(directory),
                            "WAHA_API_KEY": config["bridge_key"], "APP_WEBHOOK_SECRET": config["hook_secret"],
                            "GROUPBRIEF_BRIDGE_PORT": str(self.port),
                            "GROUPBRIEF_HOOK_URL": f"http://127.0.0.1:{app_port}/webhooks/waha",
                            "GROUPBRIEF_CHROMIUM": str(ROOT / "runtime" / "chromium" / "chrome.exe")}
        self.process = None
        self.job = None
        self.stopped = threading.Event()

    def start(self):
        node = ROOT / "runtime" / "node.exe"
        script = ROOT / "bridge" / "bridge.cjs"
        if not node.is_file() or not script.is_file() or not Path(self.environment["GROUPBRIEF_CHROMIUM"]).is_file():
            raise RuntimeError("The application runtime is incomplete. Reinstall the full GroupBrief setup package.")
        self.process = subprocess.Popen([str(node), str(script)], cwd=str(self.directory), env=self.environment,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        self.job = ChildJob(self.process)

    def monitor(self):
        restarts = 0
        while not self.stopped.wait(2):
            if self.process.poll() is None:
                continue
            if self.job:
                self.job.close()
            restarts += 1
            if restarts > 3 or self.stopped.wait(min(30, 2 ** restarts)):
                return
            try:
                self.start()
            except Exception:
                return

    def close(self):
        self.stopped.set()
        if self.process and self.process.poll() is None:
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{self.port}/internal/stop", method="POST", headers={"X-Api-Key": self.config["bridge_key"]})
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                opener.open(request, timeout=2).close()
                self.process.wait(timeout=8)
            except Exception:
                pass
        if self.job:
            self.job.close()
        if self.process and self.process.poll() is None:
            self.process.terminate()


def main():
    parser = argparse.ArgumentParser(description="GroupBrief Windows companion")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-tray", action="store_true")
    parser.add_argument("--quit", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    if args.quit:
        config = read_config(directory)
        address = dashboard(directory, config).split("/#", 1)[0]
        request_local(address + "/api/desktop/quit", config["admin_token"], "POST")
        return
    if os.name != "nt":
        raise RuntimeError("This launcher requires Windows 10/11 x64.")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    mutex_name = "GroupBrief.Desktop" if directory == DEFAULT_DATA.resolve() else "Local\\GroupBrief." + hashlib.sha256(str(directory).casefold().encode()).hexdigest()[:20]
    mutex = api.CreateMutexW(None, False, mutex_name)
    if ctypes.get_last_error() == 183:
        if not (args.background or args.no_browser):
            config = read_config(directory)
            webbrowser.open(dashboard(directory, config))
        api.CloseHandle(wintypes.HANDLE(mutex))
        return
    atexit.register(lambda: api.CloseHandle(wintypes.HANDLE(mutex)))
    config = read_config(directory)
    logging.getLogger().addHandler(logging.NullHandler())
    logging.getLogger().setLevel(logging.CRITICAL)
    sock = bind_dashboard(config.get("port", 8765))
    port = sock.getsockname()[1]
    config["port"] = port
    (directory / "local-config.json").write_text(json.dumps(config), encoding="utf-8")
    (directory / "runtime.json").write_text(json.dumps({"url": f"http://127.0.0.1:{port}", "read_token": config["read_token"], "version": "2.0.0"}), encoding="utf-8")
    bridge = BridgeProcess(directory, config, port)
    bridge.start()
    threading.Thread(target=bridge.monitor, daemon=True).start()
    atexit.register(bridge.close)
    from app.core import Engine
    from app.server import create_app
    from native.plugin_install import register_plugin
    import uvicorn
    tray = None
    server = None
    def stop(*_):
        if server:
            server.should_exit = True
    if not args.no_tray:
        import pystray
        from PIL import Image, ImageDraw
        icon_image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
        draw = ImageDraw.Draw(icon_image)
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill="#087766")
        draw.text((19, 17), "GB", fill="white", stroke_width=1)
        tray = pystray.Icon("GroupBrief", icon_image, "GroupBrief · WhatsApp assistant", menu=pystray.Menu(
            pystray.MenuItem("Open GroupBrief", lambda *_: webbrowser.open(dashboard(directory, config)), default=True),
            pystray.MenuItem("Quit GroupBrief", stop)))
        tray.run_detached()
    def notify(title, body):
        if tray is None:
            raise RuntimeError("Windows notifications require the tray application.")
        tray.notify(body[:230] + ("… Open GroupBrief." if len(body) > 230 else ""), title[:60])
    fresh = not (directory / "data" / "assistant.sqlite3").exists()
    engine = Engine(directory / "data", waha_url=f"http://127.0.0.1:{bridge.port}", waha_key=config["bridge_key"],
                    webhook_secret=config["hook_secret"], desktop_notify=notify if tray else None)
    if fresh:
        engine.update_settings({"desktop_notifications": True})
    portable_plugin = ROOT.parent if (ROOT.parent / 'plugin.json').is_file() and (ROOT.parent / 'bin/GroupBriefLink.exe').is_file() else ROOT / 'chatgpt-plugin'
    app = create_app(engine, admin_token=config["admin_token"], webhook_secret=config["hook_secret"],
                     chatgpt_token=config["read_token"], register_chatgpt=lambda: register_plugin(portable_plugin), stop_desktop=stop)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=False, log_level="critical"))
    def open_when_ready():
        if args.background or args.no_browser:
            return
        for _ in range(60):
            try:
                request_local(f"http://127.0.0.1:{port}/health", config["admin_token"])
                webbrowser.open(dashboard(directory, config))
                return
            except Exception:
                time.sleep(.5)
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.run(sockets=[sock])
    finally:
        bridge.close()
        if tray:
            tray.stop()
        engine.close()
        sock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not print exception details: runtime paths can contain credentials.
        try:
            import traceback
            directory = Path(sys.argv[sys.argv.index("--data-dir") + 1]) if "--data-dir" in sys.argv else DEFAULT_DATA
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "startup-error.json").write_text(json.dumps({"type": type(error).__name__,
                "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name} for frame in traceback.extract_tb(error.__traceback__)]}), encoding="utf-8")
        except Exception:
            pass
        if os.name == "nt" and "--no-tray" not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, "GroupBrief could not start. Reopen it, or reinstall the complete setup package. Your saved settings have been kept.", "GroupBrief", 0x10)
        raise SystemExit(1)
