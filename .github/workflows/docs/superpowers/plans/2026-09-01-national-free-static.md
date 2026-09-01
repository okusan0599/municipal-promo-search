# 全国自治体公式公示検索 v6 Free Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Actions と JSON 永続化だけで全国自治体公式公示と官公需APIを継続収集し、静的検索画面で公開できる無料版を構築する。

**Architecture:** JSONStore が自治体・公式ソース・案件の状態をローカルJSONに永続化し、既存の探索/抽出モジュールから利用する。GitHub Actions が6時間ごとに小さなバッチを実行してJSONをcommitし、静的UIは同一リポジトリの `data/projects.json` と `data/status.json` を読む。

**Tech Stack:** Python 3.12, requests, BeautifulSoup4, GitHub Actions, static HTML/JavaScript, JSON

**Spec:** `docs/superpowers/specs/2026-09-01-national-free-static-design.md`

## Global Constraints

- PostgreSQL、Render Cron Job、その他月額課金サービスを必須にしない。
- 官公需APIと自治体公式直接収集を併用する。
- 直接収集をWebサーバープロセス内で実行しない。
- 1回の収集は小さいバッチに制限する。
- v5.1 の電通フィット分類・テーマ精度を維持する。
- 既存Render Web Serviceでも静的配信できる。

---

### Task 1: JSON 永続ストア

**Files:**
- Create: `app/json_store.py`
- Test: `tests/test_json_store.py`

**Interfaces:**
- Produces: `JsonStore(data_dir)`, `upsert_municipality`, `upsert_source`, `upsert_project`, `list_municipalities`, `due_sources`, `mark_*`, `coverage_stats`, `flush`.

- [ ] Write failing tests for municipality/source/project upsert, direct-source precedence, due scheduling, and coverage.
- [ ] Run `pytest tests/test_json_store.py -v` and confirm failures because `app.json_store` does not exist.
- [ ] Implement atomic JSON read/write and the repository-compatible methods.
- [ ] Run `pytest tests/test_json_store.py -v` and confirm all pass.

### Task 2: 全国マスター投入と無料収集サイクル

**Files:**
- Create: `app/jobs/free_cycle.py`
- Modify: `app/jobs/seed_db.py`
- Modify: `app/jobs/discover_sources.py`
- Modify: `app/jobs/crawl_due_sources.py`
- Test: `tests/test_free_cycle.py`

**Interfaces:**
- Consumes: `JsonStore`; existing `RobotsAwareClient`, direct discovery/extraction, KKJ parser/classifier.
- Produces: `run_cycle(store, ...) -> dict` and module CLI `python -m app.jobs.free_cycle`.

- [ ] Write failing tests for first-run seed, known 唐津 source, bounded discovery/direct invocation, and status file generation.
- [ ] Run the focused tests and confirm failure.
- [ ] Generalize seed/discovery/crawl type hints away from SQLAlchemy repository and add `free_cycle` orchestration.
- [ ] Move KKJ cache filenames to `data/kkj_projects.json` / `data/kkj_status.json`, then merge fetched rows into JsonStore.
- [ ] Run focused tests and confirm pass.

### Task 3: 静的 UI

**Files:**
- Modify: `index.html`
- Test: `tests/test_static_ui.py`

**Interfaces:**
- Consumes: `data/projects.json`, `data/status.json`.
- Produces: API-free searchable static application.

- [ ] Write a failing contract test that rejects `/api/projects` and requires relative JSON fetch URLs.
- [ ] Run the test and confirm failure against the existing API-based UI.
- [ ] Change load logic to timestamped `data/status.json` and `data/projects.json` fetches and update sync copy.
- [ ] Run UI contract tests and JS syntax check.

### Task 4: GitHub Actions 自動更新

**Files:**
- Create: `.github/workflows/collect.yml`
- Create: `requirements.txt`
- Test: `tests/test_workflow_contract.py`

**Interfaces:**
- Produces: scheduled/manual job that collects and commits only changed `data/*.json`.

- [ ] Write failing workflow contract tests for schedule, manual dispatch, `contents: write`, concurrency, Python 3.12, free_cycle command, and conditional commit.
- [ ] Run focused tests and confirm failure.
- [ ] Create workflow and lightweight collector requirements.
- [ ] Run workflow contract tests and YAML parse validation.

### Task 5: Initial data, docs, deployment compatibility

**Files:**
- Create/normalize: `data/projects.json`, `data/municipalities.json`, `data/sources.json`, `data/status.json`, `data/kkj_projects.json`, `data/kkj_status.json`
- Modify: `data/source_seed.json`
- Modify: `README.md`
- Create: `VERSION`
- Test: `tests/test_bundle_contract.py`

**Interfaces:**
- Produces: upload-ready project usable on Render Static Site or the existing Render Web Service via `python -m http.server`.

- [ ] Write failing bundle contract tests for required data files, 唐津 seed, no DATABASE_URL requirement, and documented deployment commands.
- [ ] Run focused tests and confirm failure.
- [ ] Add initial files and deployment instructions.
- [ ] Run focused tests and confirm pass.

### Task 6: Full verification and package

**Files:**
- All project files
- Output: `/mnt/data/municipal-promo-national-free-v6.zip`

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m compileall -q app`.
- [ ] Extract the inline JavaScript from `index.html` and run `node --check`.
- [ ] Run one offline fixture-based direct-crawl smoke test.
- [ ] Zip the project excluding caches and compiled artifacts.
- [ ] List ZIP contents and verify required paths are present.
