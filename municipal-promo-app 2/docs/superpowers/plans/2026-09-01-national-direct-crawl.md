# 全国自治体公式公示ページ直接収集 v6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 現行の官公需API検索を維持しつつ、自治体公式サイトの公示ページを独立ジョブで直接収集し、PostgreSQLへ統合して同じ検索UIから検索できるv6を実装する。

**Architecture:** SQLAlchemyを使ったDB層を追加し、本番は`DATABASE_URL`のPostgreSQL、テストはSQLiteを利用する。WebサーバーはDB検索だけを行い、公式サイト探索・クロールは`app.jobs`の独立コマンドとして実行する。官公需API案件と直接収集案件は共通`projects`テーブルへupsertし、公式直接ソースを優先する。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, PostgreSQL/psycopg, requests, BeautifulSoup4, pytest

**Spec:** `docs/superpowers/specs/2026-09-01-national-direct-crawl-design.md`

## Global Constraints
- Web Service起動時と検索リクエスト中に全国クロールを実行しない。
- robots.txtを尊重し、同一ホストへのアクセスを抑制する。
- 現行v5.1の電通フィット分類とUI互換フィールドを維持する。
- 公式自治体ページを官公需APIより優先する。
- 秘密情報は環境変数に置き、GitHubへ保存しない。

---

### Task 1: Database model and repository
**Files:** Create `app/db.py`, `app/models.py`, `app/repository.py`; modify `requirements.txt`; test `tests/test_repository.py`.
**Interfaces:** `init_db()`, `get_session()`, `ProjectRepository.upsert_project()`, `ProjectRepository.list_projects()`, coverage helpers.
- [ ] Write failing SQLite repository tests for municipality/source/project upsert and official-source precedence.
- [ ] Run tests and confirm failure.
- [ ] Implement SQLAlchemy models/repository and dependencies.
- [ ] Run repository and existing tests.

### Task 2: Direct-source discovery and HTML extraction
**Files:** Create `app/direct/discovery.py`, `app/direct/extract.py`, `app/direct/http.py`; fixtures under `tests/fixtures/`; test `tests/test_direct_crawl.py`.
**Interfaces:** `discover_source_links()`, `extract_project_links()`, `extract_project()`, `RobotsAwareClient`.
- [ ] Write failing fixtures/tests for 唐津市型 procurement page, proposal page, archive/noise exclusion, date/budget extraction.
- [ ] Run tests and confirm failure.
- [ ] Implement bounded same-host discovery and extraction.
- [ ] Run direct-crawl and classifier tests.

### Task 3: Independent jobs and seeds
**Files:** Create `app/jobs/seed_db.py`, `app/jobs/discover_sources.py`, `app/jobs/crawl_due_sources.py`, `data/municipality_seed.json`, `data/source_seed.json`; test `tests/test_jobs.py`.
**Interfaces:** CLI modules runnable with `python -m app.jobs.<name>`; source failures do not abort batches.
- [ ] Write failing job tests with mocked HTTP/repository boundaries.
- [ ] Run tests and confirm failure.
- [ ] Implement seed, discovery, and due-source crawl jobs with batch limits/backoff.
- [ ] Run job tests.

### Task 4: DB-backed API, migration bridge, admin coverage and UI
**Files:** Modify `app/main.py`, `app/kkj.py`, `index.html`, `README.md`; create `app/migrate.py`; test `tests/test_api_v6.py`, update `tests/test_ui_contract.py`.
**Interfaces:** `/api/projects`, `/api/admin/source-stats`, `/api/admin/crawl-status`, `/api/admin/municipality-coverage`, `/health`; `/api/refresh` only refreshes KKJ and upserts DB, never triggers national direct crawl.
- [ ] Write failing API tests for DB-backed combined results and coverage endpoints.
- [ ] Run tests and confirm failure.
- [ ] Implement DB-backed API with JSON-cache fallback when DATABASE_URL is absent.
- [ ] Add source-system/official URL/last-checked indicators to UI without changing existing filters.
- [ ] Run full tests, compile checks and smoke tests.
