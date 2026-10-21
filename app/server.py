"""Local-only administration API and authenticated WAHA webhook receiver."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .core import Engine
from .integrations import shared_brief, shared_messages

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_BODY = 1_048_576


def create_app(engine: Engine | None = None, *, admin_token: str | None = None,
               webhook_secret: str | None = None, run_scheduler: bool = True,
               chatgpt_token: str | None = None, register_chatgpt=None, stop_desktop=None) -> FastAPI:
    token = admin_token if admin_token is not None else os.getenv("APP_ADMIN_TOKEN", "")
    hook_key = webhook_secret if webhook_secret is not None else os.getenv("APP_WEBHOOK_SECRET", "")
    read_token = chatgpt_token or ""
    if len(token) < 32 or len(hook_key) < 32:
        raise RuntimeError("Use Start.cmd to generate the local administration credentials first.")
    owned_engine = engine is None
    engine = engine or Engine(
        data_dir=Path(os.getenv("APP_DATA_DIR", "data")),
        waha_url=os.getenv("WAHA_URL", "http://waha:3000"),
        waha_key=os.getenv("WAHA_API_KEY", ""),
        webhook_secret=hook_key,
        demo=os.getenv("DEMO_MODE", "0") == "1",
    )

    async def schedule(stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await run_in_threadpool(engine.tick)
            except Exception:
                # Never emit provider bodies, messages, tokens, or exception strings.
                logging.getLogger("groupbrief").warning("A scheduled check failed; inspect the local dashboard.")
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop = asyncio.Event()
        worker = asyncio.create_task(schedule(stop)) if run_scheduler else None
        yield
        stop.set()
        if worker:
            await worker
        if owned_engine:
            engine.close()

    app = FastAPI(title="GroupBrief", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.engine = engine

    @app.middleware("http")
    async def secure_local_api(request: Request, call_next):
        # Reject DNS rebinding. Docker publishes this port only on 127.0.0.1.
        host = request.url.hostname
        if host not in {"127.0.0.1", "localhost", "::1", "assistant", "testserver"}:
            return JSONResponse({"detail": "This application is available only on this PC."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
        length = request.headers.get("content-length", "0")
        try:
            if int(length) > MAX_BODY:
                return JSONResponse({"detail": "Request too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid request length."}, status_code=400)
        # Read a bounded body even if Content-Length is absent (chunked transfer).
        if request.method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BODY:
                    return JSONResponse({"detail": "Request too large."}, status_code=413)
            request._body = bytes(body)
        if request.url.path.startswith("/api/"):
            expected = f"Bearer {token}"
            supplied = request.headers.get("authorization", "")
            administrator = hmac.compare_digest(supplied.encode(), expected.encode())
            readonly = bool(len(read_token) >= 32 and request.method == "GET" and request.url.path in {"/api/chatgpt/brief", "/api/chatgpt/status", "/api/chatgpt/messages"}
                            and hmac.compare_digest(supplied.encode(), ("Bearer " + read_token).encode()))
            if not (administrator or readonly):
                return JSONResponse({"detail": "Open GroupBrief using its desktop shortcut or launcher to sign in."}, status_code=401)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        return response

    @app.exception_handler(ValueError)
    async def invalid_input(_: Request, exc: ValueError):
        # Engine errors are intentionally human-authored and contain no request values.
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RuntimeError)
    async def service_error(_: Request, exc: RuntimeError):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        return JSONResponse({"detail": "The operation failed. Check the local dashboard and try again."}, status_code=500)

    @app.get("/health")
    def health():
        return {"status": "ok", "application": "GroupBrief", "version": "2.2.0"}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    def state():
        value = engine.state()
        value["configured"].update(desktop=bool(engine.desktop_notify), chatgpt_plugin=bool(register_chatgpt))
        return value

    @app.get("/api/chatgpt/brief")
    def chatgpt_brief():
        try:
            return shared_brief(engine)
        except PermissionError as error:
            raise HTTPException(403, str(error)) from None

    @app.get("/api/chatgpt/messages")
    def chatgpt_messages(limit: int = 30, hours: int = 24, chat_id: str | None = None, cursor: str | None = None):
        try:
            return shared_messages(engine, limit=limit, hours=hours, chat_id=chat_id, cursor=cursor)
        except PermissionError as error:
            raise HTTPException(403, str(error)) from None

    @app.get("/api/chatgpt/status")
    def chatgpt_status():
        with engine.lock:
            if not (engine.settings()["chatgpt_enabled"] or engine.settings()["chatgpt_messages_enabled"]):
                raise HTTPException(403, "ChatGPT sharing is disabled. Enable it in GroupBrief Settings first.")
            return {"application": "GroupBrief", "connection": dict(engine.connection),
                    "monitoring_allowed": engine.settings()["processing_consent"],
                    "message_sharing_enabled": engine.settings()["chatgpt_messages_enabled"],
                    "brief_sharing_enabled": engine.settings()["chatgpt_enabled"],
                    "background_analysis_enabled": engine.settings()["background_analysis_enabled"],
                    "note": "Use read_whatsapp_messages for analysis in this ChatGPT conversation without an API key. Automatic analysis is optional. Reading messages does not save tasks or schedule reminders."}

    @app.post("/api/chatgpt/register")
    def chatgpt_register():
        if not (engine.settings()["chatgpt_enabled"] or engine.settings()["chatgpt_messages_enabled"]):
            raise HTTPException(403, "Allow ChatGPT sharing in Settings before making the plugin available.")
        if register_chatgpt is None:
            raise HTTPException(503, "Use the GroupBrief Windows desktop installer for its local ChatGPT plugin.")
        return register_chatgpt()

    @app.post("/api/desktop/quit")
    def desktop_quit():
        if stop_desktop is None:
            raise HTTPException(503, "Use Stop.cmd for the Docker installation.")
        stop_desktop()
        return {"status": "stopping"}

    @app.post("/api/settings")
    def settings(payload: dict[str, Any]):
        engine.update_settings(payload)
        return {"status": "saved"}

    @app.get("/api/groups")
    def groups():
        return {"groups": engine.list_groups()}

    @app.get("/api/chats")
    def chats():
        return {"chats": engine.list_chats()}

    @app.post("/api/connect")
    def connect():
        return engine.connect()

    @app.get("/api/qr")
    def qr():
        return engine.qr()

    @app.post("/api/analyze")
    def analyze():
        return engine.analyze()

    @app.post("/api/refresh-messages")
    def refresh_messages():
        with engine.lock:
            engine._poll()
            engine.last_poll = engine.now()
            return {"connection_status": engine.connection["status"],
                    "message": "Message refresh finished. In ChatGPT, use WhatsApp and ask what needs your attention. No API analysis was run."}

    @app.patch("/api/tasks/{task_id}")
    def task_update(task_id: str, payload: dict[str, Any]):
        return engine.task_update(task_id, payload)

    @app.post("/api/test-notification")
    def notification():
        return engine.test_notification()

    @app.get("/api/export")
    def export():
        return PlainTextResponse(engine.export_markdown(), headers={
            "Content-Disposition": 'attachment; filename="groupbrief.md"'
        })

    @app.post("/webhooks/waha")
    async def webhook(request: Request):
        body = await request.body()
        signature = request.headers.get("X-Webhook-Hmac", "")
        algorithm = request.headers.get("X-Webhook-Hmac-Algorithm", "sha512")
        expected = hmac.new(hook_key.encode(), body, hashlib.sha512).hexdigest()
        if algorithm != "sha512" or not hmac.compare_digest(signature.encode(), expected.encode()):
            raise HTTPException(401, "Invalid webhook signature.")
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid webhook JSON.") from None
        if not isinstance(payload, dict):
            raise HTTPException(400, "Invalid webhook payload.")
        accepted = await run_in_threadpool(engine.ingest_event, payload)
        return {"accepted": accepted}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
