from __future__ import annotations

import json
import os
import re
from typing import Protocol

from app.direct.http import RobotsAwareClient
from app.history.extract import extract_history_records, extract_history_records_from_pdf, extract_result_document_links
from app.history.discovery import discover_history_links


class HistoryStore(Protocol):
    def due_history_sources(self, limit: int = 20) -> list[dict]: ...
    def upsert_history_award(self, row: dict): ...
    def upsert_history_source(self, row: dict): ...
    def mark_history_source_success(self, source_id: str, **kwargs) -> None: ...
    def mark_history_source_failure(self, source_id: str, message: str = "") -> None: ...
    def flush(self) -> None: ...


def _context(source: dict) -> dict:
    return {
        "municipalityCode": source.get("municipalityCode"), "municipality": source.get("municipality"),
        "organization": source.get("municipality"), "region": source.get("region"), "area": source.get("area"),
        "candidateTitle": source.get("title"),
    }


def _extract_years(*values) -> list[int]:
    text = " ".join(str(v or "") for v in values)
    years = {int(y) for y in re.findall(r"\b(20\d{2})\b", text)}
    for era, ey in re.findall(r"(令和|平成)\s*(\d{1,2})\s*年度?", text):
        years.add((2018 if era == "令和" else 1988) + int(ey))
    return sorted(y for y in years if 2000 <= y <= 2100)


def crawl_history_batch(repo: HistoryStore, client: RobotsAwareClient, limit: int = 20) -> dict:
    sources = repo.due_history_sources(limit=limit)
    detail_limit = int(os.getenv("HISTORY_DETAIL_LIMIT", "5"))
    pdf_pages = int(os.getenv("HISTORY_PDF_MAX_PAGES", "20"))
    result = {"processed": 0, "succeeded": 0, "failed": 0, "awards": 0, "documents": 0, "unchanged": 0}
    for source in sources:
        result["processed"] += 1
        try:
            if str(source.get("url", "")).lower().split("?", 1)[0].endswith(".pdf"):
                fetched = client.fetch_binary(source["url"], etag=source.get("etag"), last_modified=source.get("lastModified"))
                if fetched.not_modified:
                    repo.mark_history_source_success(source["id"], etag=source.get("etag"), last_modified=source.get("lastModified"), covered_years=_extract_years(source.get("title"), source.get("url")))
                    result["unchanged"] += 1; result["succeeded"] += 1; continue
                records = extract_history_records_from_pdf(fetched.content, source["url"], _context(source), max_pages=pdf_pages)
                for record in records:
                    repo.upsert_history_award(record); result["awards"] += 1
                repo.mark_history_source_success(source["id"], etag=fetched.etag, last_modified=fetched.last_modified, content_hash=fetched.content_hash, covered_years=_extract_years(source.get("title"), source.get("url"), *[r.get("year") for r in records]))
                result["succeeded"] += 1
                continue

            fetched = client.fetch(source["url"], etag=source.get("etag"), last_modified=source.get("lastModified"))
            if fetched.not_modified:
                repo.mark_history_source_success(source["id"], etag=source.get("etag"), last_modified=source.get("lastModified"), covered_years=_extract_years(source.get("title"), source.get("url")))
                result["unchanged"] += 1; result["succeeded"] += 1; continue
            records = extract_history_records(fetched.text, source["url"], _context(source))
            for record in records:
                repo.upsert_history_award(record); result["awards"] += 1
            nested = discover_history_links(fetched.text, source["url"], limit=detail_limit)
            pdf_docs = extract_result_document_links(fetched.text, source["url"], limit=detail_limit)
            nested_by_url = {item["url"]: item for item in nested}
            for doc in pdf_docs:
                nested_by_url.setdefault(doc["url"], {"url": doc["url"], "title": doc["title"], "sourceType": "result_pdf", "score": 10})
            for doc in nested_by_url.values():
                if doc["url"] == source["url"]:
                    continue
                repo.upsert_history_source({
                    "municipality_code": source["municipalityCode"], "url": doc["url"], "title": doc["title"],
                    "source_type": doc.get("sourceType") or "result", "priority": 1 if doc.get("score", 0) >= 10 else 3,
                    "active": True, "discovery_method": "result_archive_link",
                })
                result["documents"] += 1
            repo.mark_history_source_success(source["id"], etag=fetched.etag, last_modified=fetched.last_modified, content_hash=fetched.content_hash, covered_years=_extract_years(source.get("title"), source.get("url"), fetched.text[:3000], *[r.get("year") for r in records]))
            result["succeeded"] += 1
        except Exception as exc:
            repo.mark_history_source_failure(source["id"], str(exc))
            result["failed"] += 1
    return result


def main() -> None:
    from pathlib import Path
    from app.json_store import JsonStore
    repo = JsonStore(Path(__file__).resolve().parents[2] / "data")
    client = RobotsAwareClient(timeout=int(os.getenv("DIRECT_HTTP_TIMEOUT", "12")), min_host_interval=float(os.getenv("DIRECT_HOST_INTERVAL", "0.4")))
    result = crawl_history_batch(repo, client, limit=int(os.getenv("HISTORY_CRAWL_BATCH_SIZE", "30")))
    repo.flush()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
