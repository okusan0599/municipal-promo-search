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

app = FastAPI(title="自治体プロモーション公示検索", version="6.0")
_refresh_lock = threading.Lock()
_repo = None


def database_enabled() -> bool:
    return bool(os.getenv("DATABASE_URL"))


def get_repository():
    global _repo
    if _repo is None:
        from .db import get_database
        from .repository import ProjectRepository
        db = get_database(); db.create_all(); _repo = ProjectRepository(db)
    return _repo


def startup() -> None:
    """Initialize storage only; never launch network crawl/background threads."""
    if database_enabled():
        get_repository()


def _refresh_locked(force: bool = True) -> dict[str, Any]:
    if not _refresh_lock.acquire(blocking=False):
        return get_status()
    try:
        status = refresh_projects(force=force)
        if database_enabled():
            repo = get_repository()
            for row in get_projects(refresh_if_stale=False):
                row = {**row, "sourceSystem": row.get("sourceSystem") or "kkj"}
                repo.upsert_project(row)
        return status
    finally:
        _refresh_lock.release()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "storage": "postgresql" if database_enabled() else "json-cache",
        "version": "6.0",
    }


@app.head("/health")
def health_head() -> Response:
    return Response(status_code=200)


@app.get("/api/projects")
def projects(
    refresh: bool = Query(default=False, description="explicitly refresh bounded KKJ feed before DB read"),
) -> JSONResponse:
    try:
        if database_enabled():
            if refresh:
                _refresh_locked(force=True)
            rows = get_repository().list_projects()
        else:
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
    payload = get_status()
    if database_enabled():
        try:
            payload = {**payload, "storage": "postgresql", "coverage": get_repository().coverage_stats()}
        except Exception as exc:
            payload = {**payload, "storage": "postgresql", "dbError": str(exc)}
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})


@app.get("/api/regions")
def regions() -> JSONResponse:
    return JSONResponse(content={"prefectures": AREA_BY_PREF, "source": "JIS X0401 prefecture names"})


@app.post("/api/refresh")
def refresh(x_refresh_token: str | None = Header(default=None)) -> dict[str, Any]:
    expected = os.getenv("REFRESH_TOKEN")
    if expected and x_refresh_token != expected:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return _refresh_locked(force=True)


@app.get("/api/admin/source-stats")
def source_stats() -> JSONResponse:
    if not database_enabled():
        return JSONResponse(content={"storage": "json-cache", "directCrawl": False})
    return JSONResponse(content={"storage": "postgresql", **get_repository().source_stats()}, headers={"Cache-Control": "no-store"})


@app.get("/api/admin/municipality-coverage")
def municipality_coverage() -> JSONResponse:
    if not database_enabled():
        return JSONResponse(content={"municipalities": 0, "municipalitiesWithSources": 0, "sources": 0, "projects": 0, "storage": "json-cache"})
    return JSONResponse(content={**get_repository().coverage_stats(), "storage": "postgresql"}, headers={"Cache-Control": "no-store"})


@app.get("/api/admin/crawl-status")
def crawl_status() -> JSONResponse:
    if not database_enabled():
        return JSONResponse(content={"enabled": False, "reason": "DATABASE_URL is not configured"})
    repo = get_repository()
    sources = repo.list_sources(limit=100)
    failures = sum(1 for row in sources if row.get("failureCount", 0) > 0)
    return JSONResponse(content={"enabled": True, "sampledSources": len(sources), "failedSources": failures, "coverage": repo.coverage_stats()}, headers={"Cache-Control": "no-store"})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-store, max-age=0"})


@app.head("/")
def index_head() -> Response:
    return Response(status_code=200, headers={"Cache-Control": "no-store, max-age=0"})


if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
