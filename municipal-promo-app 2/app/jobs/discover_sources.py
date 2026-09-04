from __future__ import annotations

import json
import os
from typing import Protocol
from urllib.parse import urljoin

from app.direct.discovery import discover_source_links, discover_sitemap_urls
from app.history.discovery import discover_history_links, discover_history_sitemap_urls
from app.direct.http import RobotsAwareClient


class DiscoveryStore(Protocol):
    def upsert_source(self, row: dict): ...
    def upsert_history_source(self, row: dict): ...
    def list_municipalities(self, *, without_sources: bool, limit: int, offset: int = 0) -> list[dict]: ...
    def mark_municipality_verified(self, code: str) -> None: ...
    def flush(self) -> None: ...


def _merge_candidates(*groups: list[dict], limit: int = 20) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        for item in group:
            current = merged.get(item["url"])
            if current is None or item.get("score", 0) > current.get("score", 0):
                merged[item["url"]] = item
    return sorted(merged.values(), key=lambda x: (-x.get("score", 0), x["url"]))[:limit]


def discover_for_municipality(repo: DiscoveryStore, client: RobotsAwareClient, municipality: dict) -> int:
    url = municipality.get("officialUrl")
    if not url:
        return 0
    max_candidates = int(os.getenv("SOURCE_DISCOVERY_LIMIT", "12"))
    fetched = client.fetch(url)
    homepage = discover_source_links(fetched.text, url, limit=max_candidates)
    history_homepage = discover_history_links(fetched.text, url, limit=max_candidates)
    sitemap = []
    history_sitemap = []
    for sitemap_url in (urljoin(url, "/sitemap.xml"), urljoin(url, "sitemap.xml")):
        try:
            sm = client.fetch(sitemap_url)
            sitemap = discover_sitemap_urls(sm.text, url, limit=max_candidates)
            history_sitemap = discover_history_sitemap_urls(sm.text, url, limit=max_candidates)
            if sitemap or history_sitemap:
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
    history_candidates = _merge_candidates(history_homepage, history_sitemap, limit=max_candidates)
    for item in history_candidates:
        repo.upsert_history_source({
            "municipality_code": municipality["code"], "source_type": item["sourceType"], "url": item["url"],
            "title": item["title"], "discovery_method": "sitemap" if item.get("title") == item.get("url") else "link_discovery",
            "priority": 1 if item.get("score", 0) >= 12 else 3, "active": True,
        })
    repo.mark_municipality_verified(municipality["code"])
    return saved, len(history_candidates)


def run_batch(repo: DiscoveryStore, client: RobotsAwareClient, limit: int = 20, offset: int = 0) -> dict:
    rows = repo.list_municipalities(without_sources=True, limit=limit, offset=offset)
    result = {"processed": 0, "succeeded": 0, "failed": 0, "sourcesAdded": 0}
    for municipality in rows:
        result["processed"] += 1
        try:
            added, history_added = discover_for_municipality(repo, client, municipality)
            result["sourcesAdded"] += added
            result["historySourcesAdded"] = result.get("historySourcesAdded", 0) + history_added
            result["succeeded"] += 1
        except Exception:
            repo.mark_municipality_verified(municipality["code"])
            result["failed"] += 1
    return result


def main() -> None:
    from app.json_store import JsonStore
    from pathlib import Path
    repo = JsonStore(Path(__file__).resolve().parents[2] / "data")
    limit = int(os.getenv("DISCOVERY_BATCH_SIZE", "25"))
    client = RobotsAwareClient(timeout=int(os.getenv("DIRECT_HTTP_TIMEOUT", "12")), min_host_interval=float(os.getenv("DIRECT_HOST_INTERVAL", "0.4")))
    result = run_batch(repo, client, limit=limit)
    repo.flush()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
