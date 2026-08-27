from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .kkj import AREA_BY_PREF, get_projects, get_status, refresh_projects

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = BASE_DIR / "index.html"
DATA_DIR = BASE_DIR / "data"

app = FastAPI(title="自治体プロモーション公示検索", version="4.0")
_refresh_lock = threading.Lock()


def startup() -> None:
    """Intentionally lightweight.

    Render Free has limited memory and may restart at any time. Upstream KKJ sync is
    therefore never launched from app startup or a scheduler thread. Sync happens only
    on an explicit request and uses one bounded upstream request.
    """
    return None


def _refresh_locked(force: bool = True) -> dict[str, Any]:
    if not _refresh_lock.acquire(blocking=False):
        return get_status()
    try:
        return refresh_projects(force=force)
    finally:
        _refresh_lock.release()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now().astimezone().isoformat(timespec="seconds")}


@app.head("/health")
def health_head() -> Response:
    return Response(status_code=200)


@app.get("/api/projects")
def projects(
    refresh: bool = Query(default=True, description="refresh from KKJ when cache is stale"),
) -> JSONResponse:
    try:
        rows = get_projects(refresh_if_stale=refresh)
        return JSONResponse(content=rows, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return JSONResponse(
            content={"projects": [], "error": str(exc), "status": get_status()},
            status_code=200,
            headers={"Cache-Control": "no-store"},
        )


@app.get("/api/status")
def status() -> JSONResponse:
    return JSONResponse(content=get_status(), headers={"Cache-Control": "no-store"})


@app.get("/api/regions")
def regions() -> JSONResponse:
    return JSONResponse(content={"prefectures": AREA_BY_PREF, "source": "JIS X0401 prefecture names"})


@app.post("/api/refresh")
def refresh(x_refresh_token: str | None = Header(default=None)) -> dict[str, Any]:
    expected = os.getenv("REFRESH_TOKEN")
    if expected and x_refresh_token != expected:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return _refresh_locked(force=True)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-store, max-age=0"})


@app.head("/")
def index_head() -> Response:
    return Response(status_code=200, headers={"Cache-Control": "no-store, max-age=0"})


if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
