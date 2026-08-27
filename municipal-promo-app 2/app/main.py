from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .kkj import AREA_BY_PREF, get_projects, get_status, refresh_projects

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = BASE_DIR / "index.html"
DATA_DIR = BASE_DIR / "data"

app = FastAPI(title="自治体プロモーション公示検索", version="3.0")
_refresh_lock = threading.Lock()


def _refresh_safely(force: bool = True) -> None:
    if not _refresh_lock.acquire(blocking=False):
        return
    try:
        refresh_projects(force=force)
    finally:
        _refresh_lock.release()


def _scheduler() -> None:
    minutes = max(10, int(os.getenv("KKJ_CACHE_MINUTES", "30")))
    while True:
        time.sleep(minutes * 60)
        if os.getenv("AUTO_REFRESH", "true").lower() == "true":
            _refresh_safely(force=True)


@app.on_event("startup")
def startup() -> None:
    # Do not block deployment health checks. Fetch in the background.
    if os.getenv("AUTO_REFRESH", "true").lower() == "true":
        threading.Thread(target=_refresh_safely, kwargs={"force": False}, daemon=True).start()
    threading.Thread(target=_scheduler, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now().astimezone().isoformat(timespec="seconds")}


@app.get("/api/projects")
def projects(
    refresh: bool = Query(default=False, description="force refresh before returning data"),
) -> JSONResponse:
    try:
        rows = get_projects(refresh_if_stale=refresh)
        return JSONResponse(content=rows)
    except Exception as exc:
        # Keep the endpoint valid even if the upstream API is temporarily unavailable.
        return JSONResponse(content={"projects": [], "error": str(exc), "status": get_status()}, status_code=200)


@app.get("/api/status")
def status() -> JSONResponse:
    return JSONResponse(content=get_status())


@app.get("/api/regions")
def regions() -> JSONResponse:
    return JSONResponse(content={"prefectures": AREA_BY_PREF, "source": "JIS X0401 prefecture names"})


@app.post("/api/refresh")
def refresh(background_tasks: BackgroundTasks, x_refresh_token: str | None = Header(default=None)) -> dict[str, Any]:
    expected = os.getenv("REFRESH_TOKEN")
    if expected and x_refresh_token != expected:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    background_tasks.add_task(_refresh_safely, True)
    return {"status": "refresh started"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-store, max-age=0"})


if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
