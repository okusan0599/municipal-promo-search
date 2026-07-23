from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .crawler import DATA_FILE, STATUS_FILE, crawl_all
from .directory import DIRECTORY_FILE, DIRECTORY_STATUS_FILE

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = BASE_DIR / "index.html"
DATA_DIR = BASE_DIR / "data"

app = FastAPI(title="Municipal Promotion Search")
_refresh_lock = threading.Lock()


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError, json.JSONDecodeError, TypeError):
        return fallback


def is_stale(hours: int = 12) -> bool:
    status = read_json(STATUS_FILE, {})
    raw = status.get("updated_at")
    if not raw:
        return True
    try:
        updated = datetime.fromisoformat(raw)
        now = datetime.now(updated.tzinfo)
        return now - updated > timedelta(hours=hours)
    except ValueError:
        return True


def refresh_safely() -> None:
    if not _refresh_lock.acquire(blocking=False):
        return
    try:
        crawl_all()
    finally:
        _refresh_lock.release()


@app.on_event("startup")
def startup_refresh() -> None:
    if os.getenv("AUTO_REFRESH", "true").lower() == "true" and is_stale():
        threading.Thread(target=refresh_safely, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
def projects() -> JSONResponse:
    return JSONResponse(content=read_json(DATA_FILE, []))


@app.get("/api/status")
def status() -> JSONResponse:
    return JSONResponse(content=read_json(STATUS_FILE, {"updated_at": None, "count": 0, "sources": [], "errors": []}))


@app.get("/api/municipalities")
def municipalities() -> JSONResponse:
    return JSONResponse(content=read_json(DIRECTORY_FILE, []))


@app.get("/api/directory-status")
def directory_status() -> JSONResponse:
    return JSONResponse(content=read_json(DIRECTORY_STATUS_FILE, {"updated_at": None, "count": 0, "errors": []}))


@app.post("/api/refresh")
def refresh(background_tasks: BackgroundTasks, x_refresh_token: str | None = Header(default=None)) -> dict[str, str]:
    expected = os.getenv("REFRESH_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="REFRESH_TOKEN is not configured")
    if x_refresh_token != expected:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    background_tasks.add_task(refresh_safely)
    return {"status": "refresh started"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
