from __future__ import annotations

import json
from pathlib import Path
from app.db import get_database
from app.repository import ProjectRepository

DATA = Path(__file__).resolve().parent.parent / "data" / "projects.json"


def migrate_json_cache() -> dict:
    db = get_database(); db.create_all(); repo = ProjectRepository(db)
    rows = []
    try:
        rows = json.loads(DATA.read_text(encoding="utf-8"))
    except Exception:
        rows = []
    for row in rows if isinstance(rows, list) else []:
        repo.upsert_project({**row, "sourceSystem": row.get("sourceSystem") or "kkj"})
    return {"migrated": len(rows) if isinstance(rows, list) else 0, **repo.coverage_stats()}


if __name__ == "__main__":
    print(json.dumps(migrate_json_cache(), ensure_ascii=False))
