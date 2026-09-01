from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Municipality(Base):
    __tablename__ = "municipalities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    prefecture: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="city")
    official_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    area: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sources: Mapped[list["MunicipalSource"]] = relationship(back_populates="municipality")


class MunicipalSource(Base):
    __tablename__ = "municipal_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_id: Mapped[int] = mapped_column(ForeignKey("municipalities.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="other")
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discovery_method: Mapped[str] = mapped_column(String(32), default="manual")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    robots_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_crawl_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    needs_browser: Mapped[bool] = mapped_column(Boolean, default=False)
    municipality: Mapped[Municipality] = relationship(back_populates="sources")


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="running")
    processed: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    new_projects: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    municipality_code: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    area: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    municipality: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    notice_date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    deadline: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    presentation_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    opening_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    source_system: Mapped[str] = mapped_column(String(32), default="kkj", index=True)
    official_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data_quality: Mapped[str] = mapped_column(String(16), default="standard")
    theme: Mapped[list] = mapped_column(JSON, default=list)
    dentsu_fit_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    dentsu_fit_level: Mapped[str] = mapped_column(String(16), default="low", index=True)
    dentsu_categories: Mapped[list] = mapped_column(JSON, default=list)
    dentsu_category_labels: Mapped[list] = mapped_column(JSON, default=list)
    dentsu_signals: Mapped[list] = mapped_column(JSON, default=list)
    classification_version: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    sources: Mapped[list["ProjectSource"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectSource(Base):
    __tablename__ = "project_sources"
    __table_args__ = (UniqueConstraint("project_id", "url", name="uq_project_source"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    source_system: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    project: Mapped[Project] = relationship(back_populates="sources")
