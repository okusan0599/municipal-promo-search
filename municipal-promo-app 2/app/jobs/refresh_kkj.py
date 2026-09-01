from __future__ import annotations

import json
from app.db import get_database
from app.kkj import get_projects, refresh_projects
from app.repository import ProjectRepository


def main() -> None:
    db = get_database(); db.create_all(); repo = ProjectRepository(db)
    status = refresh_projects(force=True)
    rows = get_projects(refresh_if_stale=False)
    for row in rows:
        repo.upsert_project({**row, "sourceSystem": row.get("sourceSystem") or "kkj"})
    print(json.dumps({"kkj": status, "upserted": len(rows), **repo.coverage_stats()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
