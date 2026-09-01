from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, or_, select

from .db import Database, get_database
from .models import CrawlRun, Municipality, MunicipalSource, Project, ProjectSource


def _norm_title(value: str) -> str:
    return re.sub(r"[\s　・:：()（）【】\[\]「」『』]+", "", (value or "").lower())[:220]


def _dedupe_key(row: dict[str, Any]) -> str:
    base = "|".join([
        str(row.get("municipality") or row.get("organization") or row.get("municipalityCode") or ""),
        _norm_title(str(row.get("title") or "")),
        str(row.get("deadline") or ""),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _host(url: str | None) -> str | None:
    return urlparse(url).netloc.lower() if url else None


class ProjectRepository:
    def __init__(self, db: Database | None = None):
        self.db = db or get_database()

    def upsert_municipality(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.db.session() as s:
            obj = s.scalar(select(Municipality).where(Municipality.code == str(row["code"])))
            if obj is None:
                obj = Municipality(code=str(row["code"]), prefecture=row["prefecture"], name=row["name"])
                s.add(obj)
            for attr, key in [("prefecture","prefecture"),("name","name"),("kind","kind"),("official_url","official_url"),("area","area"),("active","active")]:
                if key in row:
                    setattr(obj, attr, row[key])
            obj.official_host = row.get("official_host") or _host(obj.official_url)
            s.flush()
            return {"id": obj.id, "code": obj.code, "prefecture": obj.prefecture, "name": obj.name, "officialUrl": obj.official_url, "area": obj.area}

    def upsert_source(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.db.session() as s:
            mun = s.scalar(select(Municipality).where(Municipality.code == str(row["municipality_code"])))
            if mun is None:
                raise ValueError(f"Unknown municipality code: {row['municipality_code']}")
            obj = s.scalar(select(MunicipalSource).where(MunicipalSource.url == row["url"]))
            if obj is None:
                obj = MunicipalSource(municipality_id=mun.id, url=row["url"])
                s.add(obj)
            for attr, key in [("source_type","source_type"),("title","title"),("discovery_method","discovery_method"),("priority","priority"),("active","active"),("robots_allowed","robots_allowed"),("next_crawl_at","next_crawl_at")]:
                if key in row:
                    setattr(obj, attr, row[key])
            s.flush()
            return {"id": obj.id, "municipalityCode": mun.code, "url": obj.url, "sourceType": obj.source_type, "priority": obj.priority}

    def upsert_project(self, row: dict[str, Any]) -> dict[str, Any]:
        key = _dedupe_key(row)
        direct = row.get("sourceSystem") == "municipality_direct"
        source_url = row.get("officialSourceUrl") or row.get("sourceUrl")
        with self.db.session() as s:
            obj = s.scalar(select(Project).where(Project.dedupe_key == key))
            if obj is None:
                obj = Project(dedupe_key=key, title=str(row.get("title") or "名称未確認"))
                s.add(obj)
                s.flush()
            should_replace = direct or obj.source_system != "municipality_direct"
            if should_replace:
                mappings = {
                    "external_id":"id", "municipality_code":"municipalityCode", "area":"area", "region":"region",
                    "municipality":"municipality", "organization":"organization", "title":"title", "summary":"summary",
                    "notice_date":"noticeDate", "deadline":"deadline", "presentation_date":"presentationDate",
                    "opening_date":"openingDate", "budget":"budget", "status":"status", "source_system":"sourceSystem",
                    "official_source_url":"officialSourceUrl", "last_checked":"lastChecked", "data_quality":"dataQuality",
                    "theme":"theme", "dentsu_fit_score":"dentsuFitScore", "dentsu_fit_level":"dentsuFitLevel",
                    "dentsu_categories":"dentsuCategories", "dentsu_category_labels":"dentsuCategoryLabels",
                    "dentsu_signals":"dentsuSignals", "classification_version":"classificationVersion",
                }
                for attr, name in mappings.items():
                    if name in row and row[name] is not None:
                        setattr(obj, attr, row[name])
                if source_url:
                    obj.primary_source_url = source_url
                if direct and source_url:
                    obj.official_source_url = source_url
                obj.updated_at = datetime.now(timezone.utc)
            if source_url:
                existing = s.scalar(select(ProjectSource).where(ProjectSource.project_id == obj.id, ProjectSource.url == source_url))
                if existing is None:
                    s.add(ProjectSource(project_id=obj.id, source_system=row.get("sourceSystem", "kkj"), url=source_url, title=row.get("title")))
            s.flush()
            return self._project_dict(obj, source_count=len(obj.sources) if obj.sources else 1)

    def list_projects(self, *, fit: str | None = None, area: str | None = None, region: str | None = None) -> list[dict[str, Any]]:
        with self.db.session() as s:
            q = select(Project)
            if fit == "high":
                q = q.where(Project.dentsu_fit_level == "high")
            elif fit in {"medium", "medium_plus"}:
                q = q.where(Project.dentsu_fit_level.in_(["high", "medium"]))
            if area:
                q = q.where(Project.area == area)
            if region:
                q = q.where(Project.region == region)
            rows = s.scalars(q.order_by(Project.deadline.asc().nullslast(), Project.notice_date.desc().nullslast())).all()
            out = []
            for obj in rows:
                count = s.scalar(select(func.count(ProjectSource.id)).where(ProjectSource.project_id == obj.id)) or 0
                out.append(self._project_dict(obj, source_count=int(count)))
            return out


    def list_municipalities(self, *, without_sources: bool = False, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self.db.session() as s:
            q = select(Municipality).where(Municipality.active.is_(True), Municipality.official_url.is_not(None))
            if without_sources:
                q = q.where(~Municipality.sources.any(MunicipalSource.active.is_(True)))
            rows = s.scalars(q.order_by(Municipality.last_verified_at.asc().nullsfirst(), Municipality.code.asc()).offset(offset).limit(limit)).all()
            return [{"code": m.code, "prefecture": m.prefecture, "name": m.name, "kind": m.kind,
                     "officialUrl": m.official_url, "officialHost": m.official_host, "area": m.area}
                    for m in rows]

    def mark_municipality_verified(self, code: str) -> None:
        with self.db.session() as s:
            obj = s.scalar(select(Municipality).where(Municipality.code == str(code)))
            if obj is not None:
                obj.last_verified_at = datetime.now(timezone.utc)

    def list_sources(self, limit: int = 1000) -> list[dict[str, Any]]:
        with self.db.session() as s:
            q = (select(MunicipalSource, Municipality).join(Municipality, MunicipalSource.municipality_id == Municipality.id)
                 .where(MunicipalSource.active.is_(True)).order_by(MunicipalSource.priority, Municipality.code).limit(limit))
            return [{"id": src.id, "municipalityCode": mun.code, "municipality": mun.name, "region": mun.prefecture,
                     "area": mun.area, "url": src.url, "sourceType": src.source_type, "title": src.title,
                     "lastSuccessAt": src.last_success_at.isoformat() if src.last_success_at else None,
                     "lastFailureAt": src.last_failure_at.isoformat() if src.last_failure_at else None, "failureCount": src.failure_count}
                    for src, mun in s.execute(q).all()]

    def due_sources(self, limit: int = 20) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        with self.db.session() as s:
            q = (select(MunicipalSource, Municipality)
                 .join(Municipality, MunicipalSource.municipality_id == Municipality.id)
                 .where(MunicipalSource.active.is_(True), or_(MunicipalSource.next_crawl_at.is_(None), MunicipalSource.next_crawl_at <= now))
                 .order_by(MunicipalSource.priority.asc(), MunicipalSource.next_crawl_at.asc().nullsfirst()).limit(limit))
            return [{"id": src.id, "url": src.url, "title": src.title, "sourceType": src.source_type,
                     "priority": src.priority, "municipalityCode": mun.code, "municipality": mun.name,
                     "region": mun.prefecture, "area": mun.area, "officialHost": mun.official_host,
                     "etag": src.etag, "lastModified": src.last_modified, "failureCount": src.failure_count}
                    for src, mun in s.execute(q).all()]

    def mark_source_success(self, source_id: int, *, etag: str | None = None, last_modified: str | None = None, content_hash: str | None = None, hours: int = 24) -> None:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        with self.db.session() as s:
            src = s.get(MunicipalSource, source_id)
            if not src: return
            src.last_success_at = now; src.failure_count = 0; src.etag = etag; src.last_modified = last_modified; src.content_hash = content_hash
            src.next_crawl_at = now + timedelta(hours=hours)

    def mark_source_failure(self, source_id: int, message: str = "") -> None:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        with self.db.session() as s:
            src = s.get(MunicipalSource, source_id)
            if not src: return
            src.last_failure_at = now; src.failure_count += 1
            hours = [6, 12, 24, 72][min(src.failure_count - 1, 3)]
            src.next_crawl_at = now + timedelta(hours=hours)

    def coverage_stats(self) -> dict[str, int]:
        with self.db.session() as s:
            municipalities = int(s.scalar(select(func.count(Municipality.id))) or 0)
            with_sources = int(s.scalar(select(func.count(func.distinct(MunicipalSource.municipality_id))).where(MunicipalSource.active.is_(True))) or 0)
            sources = int(s.scalar(select(func.count(MunicipalSource.id)).where(MunicipalSource.active.is_(True))) or 0)
            projects = int(s.scalar(select(func.count(Project.id))) or 0)
            return {"municipalities": municipalities, "municipalitiesWithSources": with_sources, "sources": sources, "projects": projects}

    def source_stats(self) -> dict[str, Any]:
        with self.db.session() as s:
            direct = int(s.scalar(select(func.count(Project.id)).where(Project.source_system == "municipality_direct")) or 0)
            kkj = int(s.scalar(select(func.count(Project.id)).where(Project.source_system == "kkj")) or 0)
        return {**self.coverage_stats(), "officialDirectProjects": direct, "kkjPrimaryProjects": kkj}

    @staticmethod
    def _project_dict(obj: Project, source_count: int) -> dict[str, Any]:
        return {
            "id": obj.external_id or f"db-{obj.id}", "municipalityCode": obj.municipality_code,
            "area": obj.area, "region": obj.region, "municipality": obj.municipality, "organization": obj.organization,
            "title": obj.title, "summary": obj.summary or "", "noticeDate": obj.notice_date, "deadline": obj.deadline,
            "presentationDate": obj.presentation_date, "openingDate": obj.opening_date, "budget": obj.budget,
            "status": obj.status, "sourceSystem": obj.source_system, "sourceCount": source_count,
            "officialSourceUrl": obj.official_source_url, "sourceUrl": obj.primary_source_url or obj.official_source_url,
            "lastChecked": obj.last_checked, "dataQuality": obj.data_quality, "theme": obj.theme or [],
            "dentsuFitScore": obj.dentsu_fit_score, "dentsuFitLevel": obj.dentsu_fit_level,
            "dentsuCategories": obj.dentsu_categories or [], "dentsuCategoryLabels": obj.dentsu_category_labels or [],
            "dentsuSignals": obj.dentsu_signals or [], "classificationVersion": obj.classification_version,
        }
