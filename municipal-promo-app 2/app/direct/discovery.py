from __future__ import annotations

from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

HIGH = {
    "プロポーザル": 10, "企画提案": 10, "提案競技": 10, "公募": 8,
    "入札": 8, "契約": 6, "調達": 8, "業務委託": 7, "委託": 5,
}
PATH_HINTS = ("nyusatsu", "procurement", "proposal", "koubo", "keiyaku", "choutatsu", "itaku")
NEGATIVE = ("過去", "archive", "アーカイブ", "工事成績", "資格者名簿")


def _same_host(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()


def discover_source_links(html: str, base_url: str, limit: int = 20) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        text = " ".join(a.stripped_strings)
        url = urljoin(base_url, a.get("href", ""))
        if not url.startswith(("http://", "https://")) or not _same_host(base_url, url):
            continue
        low = f"{text} {url}".lower()
        if any(x.lower() in low for x in NEGATIVE):
            continue
        score = sum(weight for key, weight in HIGH.items() if key.lower() in low)
        score += 4 * sum(1 for hint in PATH_HINTS if hint in low)
        if score <= 0:
            continue
        source_type = "proposal" if any(x in low for x in ("proposal", "プロポーザル", "企画提案", "提案競技")) else "procurement"
        item = {"url": url.split("#", 1)[0], "title": text[:240] or url, "sourceType": source_type, "score": score}
        if item["url"] not in out or score > out[item["url"]]["score"]:
            out[item["url"]] = item
    return sorted(out.values(), key=lambda x: (-x["score"], x["url"]))[:limit]


def discover_sitemap_urls(xml_text: str, base_url: str, limit: int = 40) -> list[dict]:
    """Extract likely procurement/proposal URLs from a sitemap document."""
    soup = BeautifulSoup(xml_text or "", "xml")
    rows = []
    seen = set()
    for loc in soup.find_all("loc"):
        url = (loc.get_text(strip=True) or "").split("#", 1)[0]
        if not url or not _same_host(base_url, url) or url in seen:
            continue
        low = url.lower()
        score = 4 * sum(1 for hint in PATH_HINTS if hint in low)
        score += sum(weight for key, weight in HIGH.items() if key.lower() in low)
        if score <= 0 or any(x.lower() in low for x in NEGATIVE):
            continue
        source_type = "proposal" if any(x in low for x in ("proposal", "koubo")) else "procurement"
        rows.append({"url": url, "title": url, "sourceType": source_type, "score": score})
        seen.add(url)
    return sorted(rows, key=lambda x: (-x["score"], x["url"]))[:limit]
