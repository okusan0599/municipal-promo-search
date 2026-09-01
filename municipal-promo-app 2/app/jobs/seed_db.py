from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Protocol

import requests

from app.kkj import AREA_BY_PREF

MUNICIPALITY_DATA_URL = os.getenv("MUNICIPALITY_DATA_URL", "https://raw.githubusercontent.com/code4fukui/localgovjp/master/localgovjp.json")
PREF_DATA_URL = os.getenv("PREF_DATA_URL", "https://raw.githubusercontent.com/code4fukui/localgovjp/master/prefjp.json")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SOURCE_SEED = DATA_DIR / "source_seed.json"


class SeedStore(Protocol):
    def upsert_municipality(self, row: dict): ...
    def upsert_source(self, row: dict): ...
    def flush(self) -> None: ...


def _kind(name: str, prefecture: str) -> str:
    if name == prefecture:
        return "prefecture"
    if name.endswith("市"):
        return "city"
    if name.endswith("区"):
        return "ward"
    if name.endswith("町"):
        return "town"
    if name.endswith("村"):
        return "village"
    return "city"


def _keep_municipality(row: dict) -> bool:
    city = str(row.get("city") or "").strip()
    pref = str(row.get("pref") or "")
    if not city or not row.get("url") or not row.get("lgcode"):
        return False
    if " " in city or "　" in city:
        return False
    if city.endswith("区") and pref != "東京都":
        return False
    return True


def seed_rows(repo: SeedStore, municipalities: Iterable[dict], prefectures: Iterable[dict]) -> int:
    count = 0
    for row in prefectures:
        name = str(row.get("pref") or "").strip()
        if not name or not row.get("url") or not row.get("lgcode"):
            continue
        repo.upsert_municipality({
            "code": str(row["lgcode"]), "prefecture": name, "name": name, "kind": "prefecture",
            "official_url": row["url"], "area": AREA_BY_PREF.get(name), "active": True,
        })
        count += 1
    for row in municipalities:
        if not _keep_municipality(row):
            continue
        pref = str(row.get("pref") or "").strip()
        city = str(row.get("city") or "").strip()
        repo.upsert_municipality({
            "code": str(row["lgcode"]), "prefecture": pref, "name": city, "kind": _kind(city, pref),
            "official_url": row["url"], "area": AREA_BY_PREF.get(pref), "active": True,
        })
        count += 1
    return count


def load_remote_rows() -> tuple[list[dict], list[dict]]:
    headers = {"User-Agent": "MunicipalPromotionSearch/6-free seed-job"}
    m = requests.get(MUNICIPALITY_DATA_URL, timeout=60, headers=headers)
    m.raise_for_status()
    p = requests.get(PREF_DATA_URL, timeout=60, headers=headers)
    p.raise_for_status()
    return m.json(), p.json()


def seed_known_sources(repo: SeedStore, source_seed: str | Path | None = None) -> int:
    path = Path(source_seed) if source_seed else SOURCE_SEED
    if not path.exists():
        return 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    saved = 0
    for row in rows:
        try:
            repo.upsert_source(row)
            saved += 1
        except ValueError:
            continue
    return saved


def main() -> None:
    from app.json_store import JsonStore
    repo = JsonStore(DATA_DIR)
    municipalities, prefectures = load_remote_rows()
    count = seed_rows(repo, municipalities, prefectures)
    sources = seed_known_sources(repo)
    repo.flush()
    print(json.dumps({"municipalitiesSeeded": count, "knownSourcesSeeded": sources, **repo.coverage_stats()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
