from __future__ import annotations

import json
import os

from app.db import get_database
from app.direct.http import RobotsAwareClient
from app.jobs.crawl_due_sources import crawl_batch
from app.jobs.discover_sources import run_batch as discover_batch
from app.jobs.seed_db import load_remote_rows, seed_known_sources, seed_rows
from app.kkj import get_projects, refresh_projects
from app.repository import ProjectRepository


def run_cycle() -> dict:
    db = get_database(); db.create_all(); repo = ProjectRepository(db)
    output: dict = {"seed": None, "kkj": None, "discovery": None, "direct": None}

    # First run only: populate the full municipality master with official top URLs.
    if repo.coverage_stats()["municipalities"] < int(os.getenv("MUNICIPALITY_SEED_MIN", "1700")):
        municipalities, prefectures = load_remote_rows()
        seeded = seed_rows(repo, municipalities, prefectures)
        known_sources = seed_known_sources(repo)
        output["seed"] = {"municipalitiesSeeded": seeded, "knownSourcesSeeded": known_sources}

    # Bounded national feed refresh. This is outside the web request process.
    try:
        kkj_status = refresh_projects(force=True)
        rows = get_projects(refresh_if_stale=False)
        for row in rows:
            repo.upsert_project({**row, "sourceSystem": row.get("sourceSystem") or "kkj"})
        output["kkj"] = {"status": kkj_status, "upserted": len(rows)}
    except Exception as exc:
        output["kkj"] = {"error": str(exc)}

    client = RobotsAwareClient(
        timeout=int(os.getenv("DIRECT_HTTP_TIMEOUT", "15")),
        min_host_interval=float(os.getenv("DIRECT_HOST_INTERVAL", "2")),
    )
    output["discovery"] = discover_batch(repo, client, limit=int(os.getenv("DISCOVERY_BATCH_SIZE", "60")))
    output["direct"] = crawl_batch(repo, client, limit=int(os.getenv("DIRECT_CRAWL_BATCH_SIZE", "30")))
    output["coverage"] = repo.coverage_stats()
    return output


if __name__ == "__main__":
    print(json.dumps(run_cycle(), ensure_ascii=False))
