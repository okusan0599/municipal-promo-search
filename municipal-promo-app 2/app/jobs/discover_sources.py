from __future__ import annotations

import json
import os
from urllib.parse import urljoin
from app.db import get_database
from app.direct.discovery import discover_source_links, discover_sitemap_urls
from app.direct.http import RobotsAwareClient
from app.repository import ProjectRepository


def _merge_candidates(*groups: list[dict], limit: int = 20) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        for item in group:
            current = merged.get(item["url"])
            if current is None or item.get("score", 0) > current.get("score", 0):
                merged[item["url"]] = item
    return sorted(merged.values(), key=lambda x: (-x.get("score", 0), x["url"]))[:limit]


def discover_for_municipality(repo: ProjectRepository, client: RobotsAwareClient, municipality: dict) -> int:
    url = municipality.get("officialUrl")
    if not url:
        return 0
    max_candidates = int(os.getenv("SOURCE_DISCOVERY_LIMIT", "12"))
    fetched = client.fetch(url)
    homepage = discover_source_links(fetched.text, url, limit=max_candidates)
    sitemap = []
    for sitemap_url in (urljoin(url, "/sitemap.xml"), urljoin(url, "sitemap.xml")):
        try:
            sm = client.fetch(sitemap_url)
            sitemap = discover_sitemap_urls(sm.text, url, limit=max_candidates)
            if sitemap:
                break
        except Exception:
            continue
    candidates = _merge_candidates(homepage, sitemap, limit=max_candidates)
    saved = 0
    for item in candidates:
        repo.upsert_source({
            "municipality_code": municipality["code"], "source_type": item["sourceType"], "url": item["url"],
            "title": item["title"], "discovery_method": "sitemap" if item.get("title") == item.get("url") else "link_discovery",
            "priority": 1 if item.get("score", 0) >= 15 else 3, "active": True,
        })
        saved += 1
    repo.mark_municipality_verified(municipality["code"])
    return saved


def run_batch(repo: ProjectRepository, client: RobotsAwareClient, limit: int = 20, offset: int = 0) -> dict:
    rows = repo.list_municipalities(without_sources=True, limit=limit, offset=offset)
    result = {"processed": 0, "succeeded": 0, "failed": 0, "sourcesAdded": 0}
    for municipality in rows:
        result["processed"] += 1
        try:
            added = discover_for_municipality(repo, client, municipality)
            result["sourcesAdded"] += added; result["succeeded"] += 1
        except Exception:
            # Mark the attempt so one permanently broken homepage cannot block national progress.
            repo.mark_municipality_verified(municipality["code"])
            result["failed"] += 1
    return result


def main() -> None:
    db = get_database(); db.create_all(); repo = ProjectRepository(db)
    limit = int(os.getenv("DISCOVERY_BATCH_SIZE", "60"))
    client = RobotsAwareClient(timeout=int(os.getenv("DIRECT_HTTP_TIMEOUT", "15")), min_host_interval=float(os.getenv("DIRECT_HOST_INTERVAL", "2")))
    print(json.dumps(run_batch(repo, client, limit=limit), ensure_ascii=False))


if __name__ == "__main__":
    main()
