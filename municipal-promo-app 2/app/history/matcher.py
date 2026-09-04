from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any

GENERIC = (
    "業務委託", "委託業務", "業務", "委託", "公募型プロポーザル", "プロポーザル", "企画提案",
    "募集", "入札", "公告", "実施", "事業", "に係る", "に関する", "について", "年度",
)
NEW_RE = re.compile(r"新規事業|新規施策|新規業務|初めて実施|初の取組|初の取り組み|新たに実施|今年度から新たに")


def _base_title(value: str | None) -> str:
    text = value or ""
    text = re.sub(r"(?:令和|平成)\s*(?:元|\d{1,2})\s*年度?", "", text)
    text = re.sub(r"\b20\d{2}\s*年度?", "", text)
    text = re.sub(r"[\s　・:：()（）【】\[\]「」『』/／_-]+", "", text.lower())
    for term in GENERIC:
        text = text.replace(term.lower(), "")
    return text[:240]


def _ngrams(value: str, n: int = 2) -> set[str]:
    return {value[i:i+n] for i in range(max(0, len(value)-n+1))} if value else set()


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def similarity_score(current: dict[str, Any], history: dict[str, Any]) -> float:
    a, b = _base_title(str(current.get("title") or "")), _base_title(str(history.get("title") or ""))
    if not a or not b:
        return 0.0
    title_sim = 1.0 if (a in b or b in a) and min(len(a), len(b)) >= 5 else _jaccard(_ngrams(a), _ngrams(b))
    current_categories = set(current.get("dentsuCategories") or [])
    history_categories = set(history.get("dentsuCategories") or [])
    cat_sim = _jaccard(current_categories, history_categories)
    score = 0.78 * title_sim + 0.22 * cat_sim
    return round(min(1.0, score), 3)


def _project_year(project: dict[str, Any]) -> int:
    title = str(project.get("title") or "").replace("元年度", "1年度")
    m = re.search(r"(令和|平成)\s*(\d{1,2})\s*年度", title)
    if m:
        return (2018 if m.group(1) == "令和" else 1988) + int(m.group(2))
    m = re.search(r"\b(20\d{2})\s*年度", title)
    if m:
        return int(m.group(1))
    for key in ("noticeDate", "deadline"):
        value = str(project.get(key) or "")
        if re.match(r"^20\d{2}-", value):
            return int(value[:4])
    return date.today().year


def _status(project: dict[str, Any], matches: list[dict], coverage_years: set[int], target_years: set[int]) -> str:
    if NEW_RE.search(f"{project.get('title') or ''} {project.get('summary') or ''}"):
        return "new_explicit"
    if matches:
        return "continuing"
    if target_years and target_years.issubset(coverage_years):
        return "new_estimated"
    return "unverified"


def enrich_projects_with_history(store, threshold: float = 0.42) -> int:
    awards_by_key: dict[str, list[dict]] = {}
    name_by_code = {str(m.get("code")): str(m.get("name") or "") for m in store.municipalities}
    for award in store.history_awards:
        keys = set()
        code = str(award.get("municipalityCode") or "")
        name = str(award.get("municipality") or "")
        if code:
            keys.add("code:" + code)
        if name:
            keys.add("name:" + name)
        for key in keys:
            awards_by_key.setdefault(key, []).append(award)

    source_years_by_key: dict[str, set[int]] = {}
    for src in store.history_sources:
        code = str(src.get("municipalityCode") or "")
        name = name_by_code.get(code, "")
        years = {int(y) for y in (src.get("coveredYears") or []) if str(y).isdigit()}
        keys = {"code:" + code} if code else set()
        if name:
            keys.add("name:" + name)
        for key in keys:
            source_years_by_key.setdefault(key, set()).update(years)

    changed = 0
    for project in store.projects:
        project_keys = []
        if project.get("municipalityCode"):
            project_keys.append("code:" + str(project.get("municipalityCode")))
        if project.get("municipality"):
            project_keys.append("name:" + str(project.get("municipality")))
        year = _project_year(project)
        target_years = {year - 1, year - 2, year - 3}
        candidates = []
        coverage_years: set[int] = set()
        raw_awards = []
        seen_award_ids = set()
        for key in project_keys:
            coverage_years.update(source_years_by_key.get(key, set()))
            for award in awards_by_key.get(key, []):
                aid = award.get("id") or award.get("dedupeKey") or id(award)
                if aid in seen_award_ids:
                    continue
                seen_award_ids.add(aid)
                raw_awards.append(award)
        for award in raw_awards:
            award_year = int(award.get("year") or 0)
            if award_year:
                coverage_years.add(award_year)
            if award_year not in target_years:
                continue
            score = similarity_score(project, award)
            if score < threshold:
                continue
            item = {
                "year": award_year,
                "title": award.get("title"),
                "vendor": award.get("vendor"),
                "amount": award.get("amount"),
                "awardDate": award.get("awardDate"),
                "sourceUrl": award.get("sourceUrl"),
                "similarity": round(score * 100),
            }
            candidates.append(item)
        candidates.sort(key=lambda x: (-x["year"], -x["similarity"], str(x.get("vendor") or "")))
        deduped = []
        seen = set()
        for item in candidates:
            key = (item["year"], item.get("vendor"), item.get("title"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        counts = Counter(item.get("vendor") for item in deduped if item.get("vendor"))
        vendor_history = [{"vendor": vendor, "count": count} for vendor, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        new_values = {
            "pastAwards": deduped,
            "vendorHistory": vendor_history,
            "historyStatus": _status(project, deduped, coverage_years, target_years),
            "historyCheckedYears": sorted(target_years, reverse=True),
            "historyCoverageYears": sorted(coverage_years & target_years, reverse=True),
        }
        if any(project.get(k) != v for k, v in new_values.items()):
            project.update(new_values)
            changed += 1
    return changed

