from __future__ import annotations

import hashlib
import json
import os
import re
import time
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .directory import build_directory

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "projects.json"
STATUS_FILE = DATA_DIR / "status.json"
CURSOR_FILE = DATA_DIR / "crawl_cursor.json"
PRIORITY_SOURCES_FILE = BASE_DIR / "sources.json"

HEADERS = {
    "User-Agent": "MunicipalPromotionSearch/2.0 (+public procurement index; low-frequency crawler)",
    "Accept-Language": "ja,en;q=0.8",
}
TIMEOUT = int(os.getenv("CRAWL_TIMEOUT", "18"))
REQUEST_DELAY = float(os.getenv("CRAWL_DELAY_SECONDS", "0.25"))
BATCH_SIZE = int(os.getenv("CRAWL_BATCH_SIZE", "35"))
MAX_NAV_PAGES = int(os.getenv("MAX_NAV_PAGES", "7"))
MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES_PER_SOURCE", "30"))
PROJECT_RETENTION_DAYS = int(os.getenv("PROJECT_RETENTION_DAYS", "180"))

CREATIVE_TERMS = [
    "プロモーション", "広報", "広告", "観光", "誘客", "情報発信", "魅力発信", "PR", "ＰＲ",
    "SNS", "ＳＮＳ", "動画", "映像", "Web", "WEB", "ウェブ", "ホームページ", "サイト制作",
    "イベント", "キャンペーン", "ブランディング", "デザイン", "クリエイティブ", "メディア",
    "移住", "交流人口", "関係人口", "シティプロモーション", "パンフレット", "冊子", "ロゴ",
    "地域活性", "ふるさと納税", "インバウンド", "デジタルマーケティング", "コンテンツ制作",
]
PROCUREMENT_TERMS = ["プロポーザル", "企画提案", "提案競技", "公募", "委託", "入札", "業者募集", "事業者募集"]
NAV_TERMS = [
    "入札", "契約", "公募", "プロポーザル", "企画提案", "事業者募集", "業務委託", "調達",
    "募集情報", "新着情報", "報道発表", "お知らせ",
]
SKIP_TERMS = ["選定結果", "審査結果", "落札結果", "契約結果", "募集終了", "受付終了", "中止"]
FILE_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".ppt", ".pptx")
THEME_RULES = {
    "観光PR": ["観光", "誘客", "周遊", "旅行", "インバウンド"],
    "広報・広告": ["広報", "広告", "PR", "ＰＲ", "情報発信", "魅力発信"],
    "SNS運用": ["SNS", "ＳＮＳ", "ソーシャル"],
    "動画制作": ["動画", "映像", "YouTube", "ユーチューブ"],
    "Web制作": ["Web", "WEB", "ウェブ", "ホームページ", "サイト制作"],
    "イベント": ["イベント", "催事", "フェア", "キャンペーン"],
    "ブランディング": ["ブランド", "ブランディング", "ロゴ", "デザイン"],
    "移住・関係人口": ["移住", "交流人口", "関係人口"],
    "メディア": ["メディア", "テレビ", "ラジオ", "新聞", "雑誌"],
    "ふるさと納税": ["ふるさと納税"],
}
ERA_BASE = {"令和": 2018, "平成": 1988}


def ensure_json_file(path: Path, default) -> None:
    """Repair browser-upload accidents where a JSON filename became a directory."""
    if path.is_dir():
        shutil.rmtree(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")



def fetch(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    ctype = response.headers.get("content-type", "")
    if ctype and "html" not in ctype.lower() and "text" not in ctype.lower():
        raise ValueError(f"unsupported content type: {ctype}")
    response.encoding = response.apparent_encoding or response.encoding
    time.sleep(REQUEST_DELAY)
    return response.text


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError, json.JSONDecodeError, TypeError):
        return fallback


def iso_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_japanese_date(text: str) -> str | None:
    text = text.replace("元年", "1年")
    patterns = [
        r"(?P<era>令和|平成)\s*(?P<ey>\d{1,2})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日",
        r"(?P<y>20\d{2})\s*[年/.-]\s*(?P<m>\d{1,2})\s*[月/.-]\s*(?P<d>\d{1,2})\s*日?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groupdict()
            year = int(groups["y"]) if groups.get("y") else ERA_BASE[groups["era"]] + int(groups["ey"])
            return iso_date(year, int(groups["m"]), int(groups["d"]))
    return None


def date_near(text: str, labels: list[str]) -> str | None:
    for label in labels:
        for match in re.finditer(label, text, flags=re.I):
            parsed = parse_japanese_date(text[match.start(): match.start() + 220])
            if parsed:
                return parsed
    return None


def extract_notice_date(soup: BeautifulSoup, text: str) -> str | None:
    for selector in ["time", "[datetime]", ".update", ".date", ".published", ".last-modified"]:
        for node in soup.select(selector):
            parsed = parse_japanese_date(node.get("datetime") or node.get_text(" ", strip=True))
            if parsed:
                return parsed
    return date_near(text, ["更新日", "掲載日", "公告日", "公示日", "公開日"])


def extract_deadline(text: str) -> str | None:
    return date_near(text, [
        "企画提案書.*?提出期限", "提案書.*?提出期限", "応募書類.*?提出期限", "提出期限",
        "受領期限", "受付期限", "参加表明書.*?期限", "参加申込.*?期限", "応募期限", "募集期間",
    ])


def extract_presentation(text: str) -> str | None:
    return date_near(text, ["プレゼンテーション", "プレゼン", "ヒアリング", "審査会", "提案審査"])


def extract_budget_man_yen(text: str) -> float | None:
    labels = ["予算限度額", "委託上限額", "契約上限額", "委託金額", "提案上限額", "予定価格", "限度額", "上限額"]
    for label in labels:
        match = re.search(label + r".{0,100}", text, flags=re.I)
        if not match:
            continue
        window = match.group(0).replace(",", "")
        amount = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(億円|万円|千円|円)", window)
        if amount:
            value = float(amount.group(1))
            return round(value * {"億円": 10000, "万円": 1, "千円": 0.1, "円": 0.0001}[amount.group(2)], 1)
    return None


def extract_themes(text: str) -> list[str]:
    lowered = text.lower()
    themes = [theme for theme, words in THEME_RULES.items() if any(word.lower() in lowered for word in words)]
    return themes or ["その他クリエイティブ"]


def candidate_title(title: str) -> bool:
    lowered = title.lower()
    return any(term.lower() in lowered for term in CREATIVE_TERMS) and any(term.lower() in lowered for term in PROCUREMENT_TERMS)


def likely_navigation(title: str, href: str) -> bool:
    hay = f"{title} {href}".lower()
    return any(term.lower() in hay for term in NAV_TERMS)


def same_official_domain(source_url: str, target_url: str) -> bool:
    src = urlparse(source_url).netloc.lower().split(":")[0]
    dst = urlparse(target_url).netloc.lower().split(":")[0]
    return dst == src or dst.endswith("." + src) or src.endswith("." + dst)


def page_links(page_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(fetch(page_url), "html.parser")
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        title = compact(anchor.get_text(" ", strip=True))
        target = urljoin(page_url, anchor["href"])
        if not target.startswith("http") or target in seen or not same_official_domain(page_url, target):
            continue
        if urlparse(target).path.lower().endswith(FILE_EXTENSIONS):
            continue
        seen.add(target)
        links.append((title, target))
    return links


def discover_navigation_pages(source: dict[str, Any]) -> list[str]:
    pages = [source["url"]]
    try:
        for title, target in page_links(source["url"]):
            if likely_navigation(title, target):
                pages.append(target)
                if len(pages) >= MAX_NAV_PAGES:
                    break
    except Exception:
        pass
    return list(dict.fromkeys(pages))


def collect_candidate_links(source: dict[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for page_url in discover_navigation_pages(source):
        try:
            links = page_links(page_url)
        except Exception:
            continue
        for title, url in links:
            if not title or not candidate_title(title) or url in seen:
                continue
            seen.add(url)
            found.append((title, url))
            if len(found) >= MAX_CANDIDATES:
                return found
    return found


def parse_project(source: dict[str, Any], hinted_title: str, url: str) -> dict[str, Any] | None:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    title_node = soup.find("h1") or soup.find("title")
    title = compact(title_node.get_text(" ", strip=True)) if title_node else hinted_title
    text = compact(soup.get_text(" ", strip=True))
    context = title + " " + text[:5000]
    if not any(term.lower() in context.lower() for term in CREATIVE_TERMS):
        return None
    if not any(term.lower() in context.lower() for term in PROCUREMENT_TERMS):
        return None

    deadline = extract_deadline(text)
    notice_date = extract_notice_date(soup, text)
    presentation = extract_presentation(text)
    budget = extract_budget_man_yen(text)
    today = date.today().isoformat()
    closed_hint = any(term in (title + text[:1500]) for term in SKIP_TERMS)
    if deadline and deadline < today:
        status = "closed"
    elif deadline and (date.fromisoformat(deadline) - date.today()).days <= 7:
        status = "soon"
    elif closed_hint:
        status = "closed"
    else:
        status = "open"

    return {
        "id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:16],
        "area": source["area"],
        "region": source["region"],
        "municipality": source.get("municipality", source["region"]),
        "noticeDate": notice_date,
        "deadline": deadline,
        "presentationDate": presentation,
        "budget": budget,
        "theme": extract_themes(context),
        "title": title,
        "summary": text[:360],
        "status": status,
        "sourceUrl": url,
        "sourceName": source.get("source_name", f'{source.get("municipality", source["region"])}公式サイト'),
        "lastChecked": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def load_priority_sources() -> list[dict[str, Any]]:
    return read_json(PRIORITY_SOURCES_FILE, [])


def select_batch(directory: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    if not directory:
        return [], 0, 0
    cursor_data = read_json(CURSOR_FILE, {"next_index": 0})
    start = int(cursor_data.get("next_index", 0)) % len(directory)
    size = min(BATCH_SIZE, len(directory))
    selected = [directory[(start + offset) % len(directory)] for offset in range(size)]
    next_index = (start + size) % len(directory)
    CURSOR_FILE.write_text(json.dumps({
        "next_index": next_index,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": len(directory),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return selected, start, next_index


def merge_projects(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {item.get("sourceUrl"): item for item in existing if item.get("sourceUrl")}
    for item in fresh:
        merged[item["sourceUrl"]] = item
    cutoff = date.today() - timedelta(days=PROJECT_RETENTION_DAYS)
    results: list[dict[str, Any]] = []
    for item in merged.values():
        deadline = item.get("deadline")
        notice = item.get("noticeDate")
        if deadline:
            try:
                if date.fromisoformat(deadline) < date.today():
                    item["status"] = "closed"
            except ValueError:
                pass
        reference = deadline or notice
        if reference:
            try:
                if date.fromisoformat(reference) < cutoff:
                    continue
            except ValueError:
                pass
        results.append(item)
    return sorted(results, key=lambda item: (item.get("status") == "closed", item.get("deadline") or "9999-12-31", item.get("noticeDate") or "0000-00-00"))


def crawl_all() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_json_file(DATA_FILE, [])
    ensure_json_file(STATUS_FILE, {"updated_at": None, "count": 0, "sources": [], "errors": []})
    ensure_json_file(CURSOR_FILE, {"next_index": 0})
    directory = build_directory()
    batch, batch_start, next_index = select_batch(directory)
    # Direct sources for major prefectural procurement pages are checked every run.
    sources = load_priority_sources() + batch
    fresh_projects: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    source_results: list[dict[str, Any]] = []
    for source in sources:
        result = {"municipality": source.get("municipality", source.get("region")), "url": source.get("url"), "candidates": 0, "projects": 0}
        try:
            links = collect_candidate_links(source)
            result["candidates"] = len(links)
        except Exception as exc:
            errors.append({"source": result["municipality"], "url": source.get("url", ""), "error": str(exc)})
            result["error"] = str(exc)
            source_results.append(result)
            continue
        for hinted_title, url in links:
            try:
                project = parse_project(source, hinted_title, url)
                if project:
                    fresh_projects.append(project)
                    result["projects"] += 1
            except Exception as exc:
                errors.append({"source": result["municipality"], "url": url, "error": str(exc)})
        source_results.append(result)

    results = merge_projects(read_json(DATA_FILE, []), fresh_projects)
    DATA_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    status = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(results),
        "new_or_updated": len(fresh_projects),
        "municipalities_total": len(directory),
        "batch_size": len(batch),
        "batch_start": batch_start,
        "next_index": next_index,
        "priority_sources": len(load_priority_sources()),
        "coverage_cycle_runs": (len(directory) + max(BATCH_SIZE, 1) - 1) // max(BATCH_SIZE, 1) if directory else 0,
        "sources_processed": source_results,
        "errors": errors[-100:],
    }
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


if __name__ == "__main__":
    print(json.dumps(crawl_all(), ensure_ascii=False, indent=2))
