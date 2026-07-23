from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "projects.json"
STATUS_FILE = DATA_DIR / "status.json"
SOURCES_FILE = BASE_DIR / "sources.json"

HEADERS = {
    "User-Agent": "MunicipalPromotionSearch/1.0 (+public procurement index; low-frequency crawler)",
    "Accept-Language": "ja,en;q=0.8",
}
TIMEOUT = 20

CREATIVE_TERMS = [
    "プロモーション", "広報", "広告", "観光", "誘客", "情報発信", "魅力発信", "PR", "ＰＲ",
    "SNS", "ＳＮＳ", "動画", "映像", "Web", "WEB", "ウェブ", "ホームページ", "サイト制作",
    "イベント", "キャンペーン", "ブランディング", "デザイン", "クリエイティブ", "メディア",
    "移住", "交流人口", "関係人口", "シティプロモーション", "パンフレット", "冊子", "ロゴ",
]
PROCUREMENT_TERMS = ["プロポーザル", "企画提案", "提案競技", "公募", "委託", "入札"]
SKIP_TERMS = ["選定結果", "審査結果", "落札結果", "契約結果", "募集終了", "受付終了", "中止"]

THEME_RULES = {
    "観光PR": ["観光", "誘客", "周遊", "旅行"],
    "広報・広告": ["広報", "広告", "PR", "ＰＲ", "情報発信", "魅力発信"],
    "SNS運用": ["SNS", "ＳＮＳ", "ソーシャル"],
    "動画制作": ["動画", "映像", "YouTube", "ユーチューブ"],
    "Web制作": ["Web", "WEB", "ウェブ", "ホームページ", "サイト制作"],
    "イベント": ["イベント", "催事", "フェア", "キャンペーン"],
    "ブランディング": ["ブランド", "ブランディング", "ロゴ", "デザイン"],
    "移住・関係人口": ["移住", "交流人口", "関係人口"],
    "メディア": ["メディア", "テレビ", "ラジオ", "新聞", "雑誌"],
}

ERA_BASE = {"令和": 2018, "平成": 1988}


def fetch(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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
        if not match:
            continue
        groups = match.groupdict()
        year = int(groups["y"]) if groups.get("y") else ERA_BASE[groups["era"]] + int(groups["ey"])
        return iso_date(year, int(groups["m"]), int(groups["d"]))
    return None


def date_near(text: str, labels: list[str]) -> str | None:
    for label in labels:
        for match in re.finditer(label, text, flags=re.I):
            window = text[match.start(): match.start() + 180]
            parsed = parse_japanese_date(window)
            if parsed:
                return parsed
    return None


def extract_notice_date(soup: BeautifulSoup, text: str) -> str | None:
    for selector in ["time", "[datetime]", ".update", ".date", ".published", ".last-modified"]:
        for node in soup.select(selector):
            raw = node.get("datetime") or node.get_text(" ", strip=True)
            parsed = parse_japanese_date(raw)
            if parsed:
                return parsed
    return date_near(text, ["更新日", "掲載日", "公告日", "公示日", "公開日"])


def extract_deadline(text: str) -> str | None:
    return date_near(text, [
        "企画提案書.*?提出期限", "提案書.*?提出期限", "応募書類.*?提出期限", "提出期限",
        "受領期限", "受付期限", "参加表明書.*?期限", "参加申込.*?期限", "応募期限",
    ])


def extract_presentation(text: str) -> str | None:
    return date_near(text, ["プレゼンテーション", "プレゼン", "ヒアリング", "審査会", "提案審査"])


def extract_budget_man_yen(text: str) -> float | None:
    labels = ["予算限度額", "委託上限額", "契約上限額", "委託金額", "提案上限額", "予定価格", "限度額"]
    for label in labels:
        match = re.search(label + r".{0,80}", text, flags=re.I)
        if not match:
            continue
        window = match.group(0).replace(",", "")
        amount = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(億円|万円|千円|円)", window)
        if not amount:
            continue
        value = float(amount.group(1))
        unit = amount.group(2)
        multiplier = {"億円": 10000, "万円": 1, "千円": 0.1, "円": 0.0001}[unit]
        return round(value * multiplier, 1)
    return None


def extract_themes(text: str) -> list[str]:
    themes = [theme for theme, words in THEME_RULES.items() if any(word.lower() in text.lower() for word in words)]
    return themes or ["その他クリエイティブ"]


def candidate_title(title: str) -> bool:
    lowered = title.lower()
    return any(term.lower() in lowered for term in CREATIVE_TERMS) and any(term.lower() in lowered for term in PROCUREMENT_TERMS)


def same_official_domain(source_url: str, target_url: str) -> bool:
    src = urlparse(source_url).netloc.split(":")[0]
    dst = urlparse(target_url).netloc.split(":")[0]
    return dst == src or dst.endswith("." + src) or src.endswith("." + dst)


def collect_candidate_links(source: dict[str, Any]) -> list[tuple[str, str]]:
    html = fetch(source["url"])
    soup = BeautifulSoup(html, "html.parser")
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        title = compact(anchor.get_text(" ", strip=True))
        if not title or not candidate_title(title):
            continue
        url = urljoin(source["url"], anchor["href"])
        if not url.startswith("http") or not same_official_domain(source["url"], url) or url in seen:
            continue
        if url.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
            continue
        seen.add(url)
        found.append((title, url))
        if len(found) >= 80:
            break
    return found


def parse_project(source: dict[str, Any], hinted_title: str, url: str) -> dict[str, Any] | None:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    title_node = soup.find("h1") or soup.find("title")
    title = compact(title_node.get_text(" ", strip=True)) if title_node else hinted_title
    text = compact(soup.get_text(" ", strip=True))
    if not any(term.lower() in (title + " " + text[:2000]).lower() for term in CREATIVE_TERMS):
        return None

    deadline = extract_deadline(text)
    notice_date = extract_notice_date(soup, text)
    presentation = extract_presentation(text)
    budget = extract_budget_man_yen(text)
    today = date.today().isoformat()
    closed_hint = any(term in (title + text[:1000]) for term in SKIP_TERMS)
    if deadline and deadline < today:
        status = "closed"
    elif deadline and (date.fromisoformat(deadline) - date.today()).days <= 7:
        status = "soon"
    elif closed_hint:
        status = "closed"
    else:
        status = "open"

    summary = text[:340]
    project_id = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return {
        "id": project_id,
        "area": source["area"],
        "region": source["region"],
        "municipality": source.get("municipality", source["region"]),
        "noticeDate": notice_date,
        "deadline": deadline,
        "presentationDate": presentation,
        "budget": budget,
        "theme": extract_themes(title + " " + text[:4000]),
        "title": title,
        "summary": summary,
        "status": status,
        "sourceUrl": url,
        "sourceName": source["source_name"],
        "lastChecked": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def crawl_all() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    projects: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source in sources:
        try:
            links = collect_candidate_links(source)
        except Exception as exc:
            errors.append({"source": source["region"], "error": str(exc)})
            continue
        for hinted_title, url in links:
            try:
                project = parse_project(source, hinted_title, url)
                if project:
                    projects.append(project)
            except Exception as exc:
                errors.append({"source": source["region"], "url": url, "error": str(exc)})

    deduped = {project["sourceUrl"]: project for project in projects}
    results = sorted(deduped.values(), key=lambda item: (item.get("deadline") or "9999-12-31", item.get("noticeDate") or "0000-00-00"))
    DATA_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    status = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(results),
        "sources": [source["region"] for source in sources],
        "errors": errors[-30:],
    }
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


if __name__ == "__main__":
    print(json.dumps(crawl_all(), ensure_ascii=False, indent=2))
