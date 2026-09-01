from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.direct.http import RobotsAwareClient
from app.json_store import JsonStore
from app.jobs.crawl_due_sources import crawl_batch
from app.jobs.discover_sources import run_batch as discover_batch
from app.jobs.seed_db import load_remote_rows, seed_known_sources, seed_rows
from app.kkj import get_projects, refresh_projects

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
STATUS_FILE = DATA_DIR / "status.json"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def run_cycle(
    *,
    store: JsonStore | None = None,
    client=None,
    municipality_rows: list[dict] | None = None,
    prefecture_rows: list[dict] | None = None,
    kkj_rows: list[dict] | None = None,
    kkj_status: dict | None = None,
    discovery_runner: Callable = discover_batch,
    direct_runner: Callable = crawl_batch,
    discovery_limit: int | None = None,
    direct_limit: int | None = None,
) -> dict:
    store = store or JsonStore(DATA_DIR)
    data_dir = store.data_dir
    status_file = data_dir / "status.json"
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    output: dict = {
        "state": "running", "started_at": started, "updated_at": started,
        "mode": "github-actions-json", "seed": None, "kkj": None, "discovery": None, "direct": None,
    }
    _write_json(status_file, output)

    normalized_statuses = store.normalize_project_statuses()
    if normalized_statuses:
        store.flush()
    output["statusNormalized"] = normalized_statuses

    errors: list[dict] = []
    try:
        if store.coverage_stats()["municipalities"] < int(os.getenv("MUNICIPALITY_SEED_MIN", "1700")):
            if municipality_rows is None or prefecture_rows is None:
                municipality_rows, prefecture_rows = load_remote_rows()
            seeded = seed_rows(store, municipality_rows or [], prefecture_rows or [])
            known = seed_known_sources(store, data_dir / "source_seed.json")
            store.flush()
            output["seed"] = {"municipalitiesSeeded": seeded, "knownSourcesSeeded": known}
    except Exception as exc:
        errors.append({"phase": "seed", "error": str(exc)[:500]})
        output["seed"] = {"error": str(exc)[:500]}

    try:
        if kkj_rows is None:
            kkj_status = refresh_projects(force=True)
            kkj_rows = get_projects(refresh_if_stale=False)
        for row in kkj_rows or []:
            store.upsert_project({**row, "sourceSystem": row.get("sourceSystem") or "kkj"})
        store.flush()
        output["kkj"] = {"count": len(kkj_rows or []), "status": kkj_status or {"state": "completed"}}
    except Exception as exc:
        errors.append({"phase": "kkj", "error": str(exc)[:500]})
        output["kkj"] = {"error": str(exc)[:500]}

    if client is None:
        client = RobotsAwareClient(
            timeout=int(os.getenv("DIRECT_HTTP_TIMEOUT", "12")),
            min_host_interval=float(os.getenv("DIRECT_HOST_INTERVAL", "0.4")),
        )
    discovery_limit = discovery_limit if discovery_limit is not None else int(os.getenv("DISCOVERY_BATCH_SIZE", "25"))
    direct_limit = direct_limit if direct_limit is not None else int(os.getenv("DIRECT_CRAWL_BATCH_SIZE", "12"))

    try:
        output["discovery"] = discovery_runner(store, client, limit=discovery_limit)
        store.flush()
    except Exception as exc:
        errors.append({"phase": "discovery", "error": str(exc)[:500]})
        output["discovery"] = {"error": str(exc)[:500]}

    try:
        output["direct"] = direct_runner(store, client, limit=direct_limit)
        store.flush()
    except Exception as exc:
        errors.append({"phase": "direct", "error": str(exc)[:500]})
        output["direct"] = {"error": str(exc)[:500]}

    finished = datetime.now().astimezone().isoformat(timespec="seconds")
    output.update({
        "state": "completed" if not errors else "partial",
        "updated_at": finished,
        "coverage": store.coverage_stats(),
        "sourceStats": store.source_stats(),
        "errors": errors,
        "message": "GitHub Actionsで全国自治体公式サイトと官公需APIを分割収集しています。",
    })
    _write_json(status_file, output)
    store.flush()
    return output


def main() -> None:
    print(json.dumps(run_cycle(), ensure_ascii=False))


if __name__ == "__main__":
    main()
