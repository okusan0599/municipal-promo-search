# Dentsu Fit Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Dentsu-fit scoring, business-domain filtering, and broader nationwide creative/consulting/AI discovery to the stable municipal procurement search without reintroducing Render startup instability.

**Architecture:** Keep the existing one-request KKJ sync and enrich each parsed project through a standalone deterministic classifier. Expose classification fields in the existing `/api/projects` response and add client-side filters and badges without changing the API route shape. Direct municipal-site crawling remains a separate v6 subsystem.

**Tech Stack:** Python 3.12, FastAPI, requests, ElementTree, vanilla HTML/CSS/JavaScript, pytest

**Spec:** `docs/superpowers/specs/2026-08-28-dentsu-fit-search-design.md`

## Global Constraints

- Render Free stability: no background sync on startup.
- One KKJ upstream request per refresh.
- `KKJ_COUNT_PER_QUERY` remains bounded to 250; recommended environment value is 120.
- Existing `/api/projects`, `/api/status`, `/health`, and `/` routes remain compatible.
- Default UI visibility is Dentsu fit `medium+`, not all projects.
- Low-fit projects remain retrievable by selecting `all`; they are not deleted from the cache.

---

### Task 1: Deterministic Dentsu-fit classifier

**Files:**
- Create: `app/classifier.py`
- Create: `tests/test_classifier.py`

**Interfaces:**
- Consumes: normalized plain-text project corpus (`str`).
- Produces: `classify_dentsu_fit(text: str) -> dict[str, Any]` with keys `score`, `level`, `categories`, `category_labels`, `signals`.

- [ ] **Step 1: Write failing tests for high-fit communications/AI and low-fit construction**

```python
from app.classifier import classify_dentsu_fit


def test_pr_ai_strategy_is_high_fit():
    result = classify_dentsu_fit("生成AIを活用した広報コミュニケーション戦略策定及びプロモーション業務委託")
    assert result["level"] == "high"
    assert result["score"] >= 70
    assert "ai_data_dx" in result["categories"]
    assert "pr_communications" in result["categories"]
    assert "consulting_strategy" in result["categories"]


def test_road_construction_is_low_fit():
    result = classify_dentsu_fit("市道舗装改修工事 道路施工及び資材調達")
    assert result["level"] == "low"
    assert result["score"] < 45
```

- [ ] **Step 2: Run classifier tests and verify RED**

Run: `pytest tests/test_classifier.py -v`
Expected: FAIL because `app.classifier` does not exist.

- [ ] **Step 3: Implement keyword categories, positive/negative scoring, and level thresholds**

Create constants for all 11 category IDs and labels from the spec. Implement normalized case-insensitive matching, cap score to `0..100`, deduplicate signals, and return signals at maximum length 8.

- [ ] **Step 4: Run classifier tests and verify GREEN**

Run: `pytest tests/test_classifier.py -v`
Expected: 2 passed.

- [ ] **Step 5: Add category coverage tests**

```python
import pytest
from app.classifier import classify_dentsu_fit

@pytest.mark.parametrize("text,category", [
    ("イベント企画運営業務", "events_experience"),
    ("観光地域ブランディング及び誘客プロモーション", "tourism_place_branding"),
    ("市場調査及びマーケティング分析", "research_marketing"),
    ("公式SNSデジタルマーケティング運用", "digital_social"),
    ("Webサイト及びアプリ開発", "web_app_service"),
])
def test_expected_category(text, category):
    assert category in classify_dentsu_fit(text)["categories"]
```

- [ ] **Step 6: Run classifier suite**

Run: `pytest tests/test_classifier.py -v`
Expected: all tests pass.

### Task 2: Enrich KKJ projects and broaden search query

**Files:**
- Modify: `app/kkj.py`
- Create: `tests/test_project_enrichment.py`
- Modify: `tests/test_stability.py`

**Interfaces:**
- Consumes: `classify_dentsu_fit(text)` from Task 1.
- Produces: every parsed project contains `dentsuFitScore`, `dentsuFitLevel`, `dentsuCategories`, `dentsuCategoryLabels`, `dentsuSignals`.

- [ ] **Step 1: Write failing enrichment test using `_parse_xml`**

Construct a minimal KKJ XML `SearchResult` whose title is `生成AIを活用した広報戦略策定業務` and assert the five Dentsu fields are present and `dentsuFitLevel == "high"`.

- [ ] **Step 2: Run enrichment test and verify RED**

Run: `pytest tests/test_project_enrichment.py -v`
Expected: FAIL due to missing Dentsu fields.

- [ ] **Step 3: Import and call classifier from `_parse_xml`**

After `corpus = f"{title} {description}"`, call `fit = classify_dentsu_fit(corpus)` and map its fields to the project output using the exact field names from the spec.

- [ ] **Step 4: Expand `COMBINED_QUERY`**

Add these OR terms while retaining a single `QUERY_GROUPS = [COMBINED_QUERY]`: `コンサルティング`, `戦略策定`, `基本構想`, `事業戦略`, `マーケティング`, `市場調査`, `アンケート`, `調査分析`, `AI`, `生成AI`, `人工知能`, `データ分析`, `データ活用`, `DX`, `デジタル活用`, `コミュニケーション`, `広報戦略`, `パブリシティ`.

- [ ] **Step 5: Run enrichment and stability tests**

Run: `pytest tests/test_project_enrichment.py tests/test_stability.py -v`
Expected: all pass, including `len(calls) == 1` upstream request assertion.

### Task 3: UI fit filter and multi-category selection

**Files:**
- Modify: `index.html`
- Create: `tests/test_ui_contract.py`

**Interfaces:**
- Consumes: new project fields from Task 2.
- Produces: DOM controls `#fitLevel` and category checkboxes with `data-dentsu-category`.

- [ ] **Step 1: Write failing static UI contract tests**

```python
from pathlib import Path

HTML = Path("index.html").read_text(encoding="utf-8")

def test_default_fit_filter_is_medium_plus():
    assert 'id="fitLevel"' in HTML
    assert '<option value="medium+" selected>' in HTML

def test_category_filter_contract_exists():
    assert 'data-dentsu-category=' in HTML
    assert 'dentsuCategories' in HTML
```

- [ ] **Step 2: Run UI contract test and verify RED**

Run: `pytest tests/test_ui_contract.py -v`
Expected: FAIL because controls do not exist.

- [ ] **Step 3: Add controls**

Add a select labelled `電通関連度` with options `medium+` selected, `high`, `all`. Add 11 category checkboxes/chips matching the IDs and Japanese labels from the spec.

- [ ] **Step 4: Normalize Dentsu fields in JavaScript**

Extend `normalizedProject(p)` with defaults: score `0`, level `low`, categories `[]`, labels `[]`, signals `[]`.

- [ ] **Step 5: Add render filtering**

Before budget/date filters, apply the fit-level rule and OR-match any checked Dentsu categories. Include `dentsuCategoryLabels` and signals in keyword haystack.

- [ ] **Step 6: Add card badges**

Render `関連度 高/中/低` with distinct CSS classes and Dentsu category chips ahead of the existing theme chips.

- [ ] **Step 7: Wire reset behavior**

Reset `fitLevel` to `medium+` and clear all category checkboxes.

- [ ] **Step 8: Run UI contract tests**

Run: `pytest tests/test_ui_contract.py -v`
Expected: all pass.

### Task 4: End-to-end API regression and documentation

**Files:**
- Modify: `tests/test_stability.py`
- Modify: `README.md`
- Modify: `data/status.json` only if needed to remove stale demo state

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: verified deployable package and operator instructions.

- [ ] **Step 1: Extend API endpoint test**

In the fake project used by `test_projects_endpoint_refreshes_with_one_request`, include the five Dentsu fields and assert the API returns `dentsuFitLevel` and `dentsuCategories` unchanged.

- [ ] **Step 2: Update README**

Document the default `medium+` behavior, all 11 categories, nationwide KKJ coverage, recommended environment values, and explicitly state that direct municipal-site collection is the next v6 phase.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: zero failures.

- [ ] **Step 4: Run syntax and import checks**

Run: `python -m compileall app tests`
Expected: exit code 0.

- [ ] **Step 5: Run local FastAPI smoke test**

Run a `TestClient` script that asserts `GET /health == 200`, `HEAD /health == 200`, `GET /api/regions == 200`, and `GET /api/projects?refresh=false == 200`.
Expected: all assertions succeed without network access.

- [ ] **Step 6: Package the release**

Create `/mnt/data/municipal-promo-dentsu-fit-v5.zip` excluding caches and `.pyc` files.
