from __future__ import annotations

import json
import os

from app.db import get_database
from app.direct.extract import extract_project, extract_project_links
from app.direct.http import RobotsAwareClient
from app.repository import ProjectRepository


def crawl_batch(repo: ProjectRepository, client: RobotsAwareClient, limit: int = 20) -> dict:
    sources = repo.due_sources(limit=limit)
    result = {"processed": 0, "succeeded": 0, "failed": 0, "projects": 0, "unchanged": 0}
    detail_limit = int(os.getenv("DIRECT_DETAIL_LIMIT", "30"))
    for source in sources:
        result["processed"] += 1
        try:
            fetched = client.fetch(source["url"], etag=source.get("etag"), last_modified=source.get("lastModified"))
            if getattr(fetched, "not_modified", False):
                repo.mark_source_success(source["id"], etag=source.get("etag"), last_modified=source.get("lastModified"))
                result["unchanged"] += 1; result["succeeded"] += 1; continue
            links = extract_project_links(fetched.text, source["url"], limit=detail_limit)
            for link in links:
                try:
                    page = client.fetch(link["url"])
                    project = extract_project(page.text, link["url"], {**source, "candidateTitle": link["title"]})
                    repo.upsert_project(project); result["projects"] += 1
                except Exception:
                    continue
            repo.mark_source_success(source["id"], etag=getattr(fetched, "etag", None), last_modified=getattr(fetched, "last_modified", None), content_hash=getattr(fetched, "content_hash", None), hours=6 if source.get("priority") == 1 else 24)
            result["succeeded"] += 1
        except Exception as exc:
            repo.mark_source_failure(source["id"], str(exc)); result["failed"] += 1
    return result


def main() -> None:
    db = get_database(); db.create_all(); repo = ProjectRepository(db)
    client = RobotsAwareClient(timeout=int(os.getenv("DIRECT_HTTP_TIMEOUT", "15")), min_host_interval=float(os.getenv("DIRECT_HOST_INTERVAL", "2")))
    result = crawl_batch(repo, client, limit=int(os.getenv("DIRECT_CRAWL_BATCH_SIZE", "20")))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
