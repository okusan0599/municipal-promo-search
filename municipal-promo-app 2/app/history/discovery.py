from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

RESULT_TERMS = {
    "落札結果": 12,
    "入札結果": 12,
    "契約結果": 12,
    "選定結果": 12,
    "審査結果": 12,
    "結果公表": 10,
    "プロポーザル結果": 14,
    "受託候補者": 10,
    "優先交渉権者": 10,
    "契約状況": 9,
    "契約実績": 9,
    "随意契約": 7,
    "落札者": 8,
    "契約者": 8,
    "委託先": 7,
    "過去の入札": 8,
    "過去の契約": 8,
}
PATH_HINTS = (
    "kekka", "result", "results", "rakusatsu", "keiyakukekka", "selection",
    "shinsa", "award", "contract-result", "nyusatsu-kekka",
)
NEGATIVE = ("工事成績", "有資格者", "名簿", "様式", "申請書", "マニュアル", "faq")


def _same_host(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()


def _score(label: str, url: str) -> int:
    low = f"{label} {url}".lower()
    if any(x.lower() in low for x in NEGATIVE):
        return 0
    score = sum(weight for term, weight in RESULT_TERMS.items() if term.lower() in low)
    score += 4 * sum(1 for hint in PATH_HINTS if hint in low)
    if re.search(r"\.(pdf|xlsx?|csv)($|\?)", url, re.I):
        score += 2
    return score


def discover_history_links(html: str, base_url: str, limit: int = 30) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        label = " ".join(a.stripped_strings).strip()
        url = urljoin(base_url, a.get("href", "")).split("#", 1)[0]
        if not url.startswith(("http://", "https://")) or not _same_host(base_url, url):
            continue
        score = _score(label, url)
        if score <= 0:
            continue
        source_type = "result_pdf" if re.search(r"\.pdf($|\?)", url, re.I) else "result"
        row = {"url": url, "title": label[:260] or url, "sourceType": source_type, "score": score}
        current = out.get(url)
        if current is None or score > current["score"]:
            out[url] = row
    return sorted(out.values(), key=lambda x: (-x["score"], x["url"]))[:limit]


def discover_history_sitemap_urls(xml_text: str, base_url: str, limit: int = 50) -> list[dict]:
    soup = BeautifulSoup(xml_text or "", "xml")
    out = []
    seen = set()
    for loc in soup.find_all("loc"):
        url = (loc.get_text(strip=True) or "").split("#", 1)[0]
        if not url or url in seen or not _same_host(base_url, url):
            continue
        score = _score("", url)
        if score <= 0:
            continue
        out.append({"url": url, "title": url, "sourceType": "result_pdf" if url.lower().endswith(".pdf") else "result", "score": score})
        seen.add(url)
    return sorted(out, key=lambda x: (-x["score"], x["url"]))[:limit]
