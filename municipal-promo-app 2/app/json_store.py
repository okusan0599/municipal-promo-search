from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.project_status import project_status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _host(url: str | None) -> str | None:
    return urlparse(url).netloc.lower() if url else None


def _norm_title(value: str) -> str:
    return re.sub(r"[\s　・:：()（）【】\[\]「」『』]+", "", (value or "").lower())[:220]


def _dedupe_key(row: dict[str, Any]) -> str:
    base = "|".join([
        str(row.get("municipality") or row.get("organization") or row.get("municipalityCode") or ""),
        _norm_title(str(row.get("title") or "")),
        str(row.get("deadline") or ""),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _source_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


class JsonStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.municipalities_path = self.data_dir / "municipalities.json"
        self.sources_path = self.data_dir / "sources.json"
        self.projects_path = self.data_dir / "projects.json"
        self.municipalities = self._read(self.municipalities_path, [])
        self.sources = self._read(self.sources_path, [])
        self.projects = self._read(self.projects_path, [])

    @staticmethod
    def _read(path: Path, fallback: Any) -> Any:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, type(fallback)) else fallback
        except Exception:
            return fallback

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def flush(self) -> None:
        self._write(self.municipalities_path, self.municipalities)
        self._write(self.sources_path, self.sources)
        self._write(self.projects_path, self.projects)

    def upsert_municipality(self, row: dict[str, Any]) -> dict[str, Any]:
        code = str(row["code"])
        obj = next((m for m in self.municipalities if str(m.get("code")) == code), None)
        if obj is None:
            obj = {"code": code}
            self.municipalities.append(obj)
        mapping = {
            "prefecture": "prefecture", "name": "name", "kind": "kind", "official_url": "officialUrl",
            "officialUrl": "officialUrl", "area": "area", "active": "active",
        }
        for key, target in mapping.items():
            if key in row:
                obj[target] = row[key]
        obj["officialHost"] = row.get("official_host") or _host(obj.get("officialUrl"))
        obj.setdefault("active", True)
        obj.setdefault("lastVerifiedAt", None)
        return {"code": code, "prefecture": obj.get("prefecture"), "name": obj.get("name"),
                "officialUrl": obj.get("officialUrl"), "area": obj.get("area")}

    def upsert_source(self, row: dict[str, Any]) -> dict[str, Any]:
        code = str(row["municipality_code"])
        municipality = next((m for m in self.municipalities if str(m.get("code")) == code), None)
        if municipality is None:
            raise ValueError(f"Unknown municipality code: {code}")
        url = str(row["url"])
        obj = next((s for s in self.sources if s.get("url") == url), None)
        if obj is None:
            obj = {"id": _source_id(url), "municipalityCode": code, "url": url, "failureCount": 0,
                   "lastSuccessAt": None, "lastFailureAt": None, "nextCrawlAt": None}
            self.sources.append(obj)
        mapping = {
            "source_type": "sourceType", "title": "title", "discovery_method": "discoveryMethod",
            "priority": "priority", "active": "active", "robots_allowed": "robotsAllowed",
            "next_crawl_at": "nextCrawlAt",
        }
        for key, target in mapping.items():
            if key in row:
                value = row[key]
                obj[target] = _iso(value) if isinstance(value, datetime) else value
        obj.setdefault("sourceType", "procurement")
        obj.setdefault("priority", 3)
        obj.setdefault("active", True)
        return {"id": obj["id"], "municipalityCode": code, "url": url,
                "sourceType": obj.get("sourceType"), "priority": obj.get("priority")}

    def normalize_project_statuses(self) -> int:
        changed = 0
        for obj in self.projects:
            detected = project_status(
                obj.get("deadline"),
                obj.get("openingDate"),
                title=obj.get("title"),
                summary=obj.get("summary"),
            )
            current = obj.get("status")
            if current == "closed":
                continue
            if detected != "unknown" and detected != current:
                obj["status"] = detected
                changed += 1
        return changed

    def upsert_project(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        detected = project_status(
            row.get("deadline"), row.get("openingDate"),
            title=row.get("title"), summary=row.get("summary"),
        )
        if row.get("status") != "closed" and detected != "unknown":
            row["status"] = detected
        key = _dedupe_key(row)
        obj = next((p for p in self.projects if p.get("dedupeKey") == key or p.get("_dedupeKey") == key), None)
        if obj is None:
            obj = {"dedupeKey": key, "sourceRefs": []}
            self.projects.append(obj)
        incoming_direct = row.get("sourceSystem") == "municipality_direct"
        existing_direct = obj.get("sourceSystem") == "municipality_direct"
        source_url = row.get("officialSourceUrl") or row.get("sourceUrl")
        if not existing_direct or incoming_direct:
            for k, v in row.items():
                if v is not None:
                    obj[k] = v
            if incoming_direct and source_url:
                obj["officialSourceUrl"] = source_url
            obj["lastChecked"] = row.get("lastChecked") or _iso(_now())
        refs = obj.setdefault("sourceRefs", obj.pop("_sources", []))
        if source_url:
            source_entry = {"sourceSystem": row.get("sourceSystem") or "kkj", "url": source_url}
            if not any(s.get("url") == source_url for s in refs):
                refs.append(source_entry)
        obj["sourceCount"] = max(1, len(refs))
        return {k: v for k, v in obj.items() if k not in {"dedupeKey", "sourceRefs"} and not k.startswith("_")}

    def list_projects(self, *, fit: str | None = None, area: str | None = None, region: str | None = None) -> list[dict[str, Any]]:
        rows = []
        for obj in self.projects:
            if fit == "high" and obj.get("dentsuFitLevel") != "high":
                continue
            if fit in {"medium", "medium_plus"} and obj.get("dentsuFitLevel") not in {"high", "medium"}:
                continue
            if area and obj.get("area") != area:
                continue
            if region and obj.get("region") != region:
                continue
            item = {k: v for k, v in obj.items() if k not in {"dedupeKey", "sourceRefs"} and not k.startswith("_")}
            item["sourceCount"] = max(1, len(obj.get("sourceRefs", [])) or int(item.get("sourceCount") or 1))
            rows.append(item)
        return sorted(rows, key=lambda p: (p.get("status") == "closed", p.get("deadline") or "9999-12-31", p.get("noticeDate") or "0000-00-00"))

    def list_municipalities(self, *, without_sources: bool = False, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        source_codes = {str(s.get("municipalityCode")) for s in self.sources if s.get("active", True)}
        rows = [m for m in self.municipalities if m.get("active", True) and m.get("officialUrl")]
        if without_sources:
            rows = [m for m in rows if str(m.get("code")) not in source_codes]
        rows.sort(key=lambda m: (m.get("lastVerifiedAt") or "", str(m.get("code") or "")))
        out = []
        for m in rows[offset:offset + limit]:
            out.append({"code": str(m.get("code")), "prefecture": m.get("prefecture"), "name": m.get("name"),
                        "kind": m.get("kind"), "officialUrl": m.get("officialUrl"), "officialHost": m.get("officialHost"),
                        "area": m.get("area")})
        return out

    def mark_municipality_verified(self, code: str) -> None:
        obj = next((m for m in self.municipalities if str(m.get("code")) == str(code)), None)
        if obj is not None:
            obj["lastVerifiedAt"] = _iso(_now())

    def list_sources(self, limit: int = 1000) -> list[dict[str, Any]]:
        mun = {str(m.get("code")): m for m in self.municipalities}
        rows = []
        for src in self.sources:
            if not src.get("active", True):
                continue
            m = mun.get(str(src.get("municipalityCode")), {})
            rows.append({**src, "municipality": m.get("name"), "region": m.get("prefecture"), "area": m.get("area")})
        rows.sort(key=lambda x: (x.get("priority", 3), x.get("municipalityCode", "")))
        return rows[:limit]

    def due_sources(self, limit: int = 20) -> list[dict[str, Any]]:
        now = _now()
        mun = {str(m.get("code")): m for m in self.municipalities}
        rows = []
        for src in self.sources:
            if not src.get("active", True):
                continue
            due = _parse(src.get("nextCrawlAt"))
            if due and due > now:
                continue
            m = mun.get(str(src.get("municipalityCode")), {})
            rows.append({**src, "municipality": m.get("name"), "region": m.get("prefecture"), "area": m.get("area"),
                         "officialHost": m.get("officialHost")})
        rows.sort(key=lambda x: (x.get("priority", 3), x.get("nextCrawlAt") or ""))
        return rows[:limit]

    def mark_source_success(self, source_id: str, *, etag: str | None = None, last_modified: str | None = None,
                            content_hash: str | None = None, hours: int = 24) -> None:
        src = next((s for s in self.sources if str(s.get("id")) == str(source_id)), None)
        if not src:
            return
        now = _now()
        src.update({"lastSuccessAt": _iso(now), "failureCount": 0, "etag": etag, "lastModified": last_modified,
                    "contentHash": content_hash, "nextCrawlAt": _iso(now + timedelta(hours=hours))})

    def mark_source_failure(self, source_id: str, message: str = "") -> None:
        src = next((s for s in self.sources if str(s.get("id")) == str(source_id)), None)
        if not src:
            return
        now = _now()
        failures = int(src.get("failureCount") or 0) + 1
        hours = [6, 12, 24, 72][min(failures - 1, 3)]
        src.update({"lastFailureAt": _iso(now), "failureCount": failures, "lastError": message[:500],
                    "nextCrawlAt": _iso(now + timedelta(hours=hours))})

    def coverage_stats(self) -> dict[str, Any]:
        municipality_codes = {str(m.get("code")) for m in self.municipalities}
        active_sources = [s for s in self.sources if s.get("active", True)]
        with_sources = {str(s.get("municipalityCode")) for s in active_sources if str(s.get("municipalityCode")) in municipality_codes}
        visited = sum(1 for m in self.municipalities if m.get("lastVerifiedAt"))
        total = len(self.municipalities)
        rate = round((visited / total * 100), 1) if total else 0.0
        projects_with_deadline = sum(1 for p in self.projects if p.get("deadline"))
        return {"municipalities": total, "municipalitiesVisited": visited, "municipalityCoverageRate": rate,
                "municipalitiesWithSources": len(with_sources), "sources": len(active_sources),
                "projects": len(self.projects), "projectsWithDeadline": projects_with_deadline}

    def source_stats(self) -> dict[str, Any]:
        direct = sum(1 for p in self.projects if p.get("sourceSystem") == "municipality_direct")
        kkj = sum(1 for p in self.projects if p.get("sourceSystem") != "municipality_direct")
        return {**self.coverage_stats(), "officialDirectProjects": direct, "kkjPrimaryProjects": kkj}
