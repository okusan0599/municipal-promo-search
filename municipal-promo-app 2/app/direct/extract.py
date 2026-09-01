from __future__ import annotations

import hashlib
import re
from datetime import date
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from app.classifier import classify_project, clean_project_description
from app.kkj import _themes

POSITIVE = ("プロポーザル", "企画提案", "提案競技", "公募", "業務委託", "委託", "入札公告", "募集要領", "実施要領")
NEGATIVE = ("過去", "archive", "アーカイブ", "工事", "修繕", "舗装", "清掃", "警備", "物品", "備品", "給食")
ERA_BASE = {"令和": 2018, "平成": 1988}


def _main(soup: BeautifulSoup):
    return soup.find("main") or soup.find("article") or soup.find(id=re.compile(r"^(main|content|contents)$", re.I)) or soup.body or soup


def _same_host(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()


def extract_project_links(html: str, base_url: str, limit: int = 80) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    root = _main(soup)
    rows = []
    seen = set()
    for a in root.find_all("a", href=True):
        text = " ".join(a.stripped_strings).strip()
        url = urljoin(base_url, a["href"]).split("#", 1)[0]
        low = f"{text} {url}".lower()
        if not _same_host(base_url, url) or url in seen:
            continue
        if any(x.lower() in low for x in NEGATIVE):
            continue
        score = sum(5 for x in POSITIVE if x.lower() in low)
        if score <= 0:
            continue
        if re.search(r"/(20\d{2}|r\d{1,2}|reiwa\d+)/?$", low):
            continue
        seen.add(url)
        rows.append({"url": url, "title": text[:300], "score": score})
    return sorted(rows, key=lambda x: (-x["score"], x["url"]))[:limit]


def _jp_date(text: str) -> str | None:
    text = (text or "").replace("元年", "1年")
    for pattern in (
        r"(?P<era>令和|平成)\s*(?P<ey>\d{1,2})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日",
        r"(?P<y>20\d{2})\s*[年/.-]\s*(?P<m>\d{1,2})\s*[月/.-]\s*(?P<d>\d{1,2})\s*日?",
    ):
        m = re.search(pattern, text)
        if not m:
            continue
        g = m.groupdict()
        year = int(g["y"]) if g.get("y") else ERA_BASE[g["era"]] + int(g["ey"])
        try:
            return date(year, int(g["m"]), int(g["d"])).isoformat()
        except ValueError:
            pass
    return None


def _near(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        for m in re.finditer(label, text, re.I):
            found = _jp_date(text[m.start():m.start()+220])
            if found:
                return found
    return None


def _budget(text: str) -> float | None:
    normalized = (text or "").replace(",", "").replace("，", "")
    for label in ("予算限度額", "委託上限額", "契約上限額", "提案上限額", "予定価格", "契約限度額", "予算額", "上限額"):
        m = re.search(re.escape(label) + r".{0,120}", normalized, re.I)
        if not m:
            continue
        amount = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(億円|万円|千円|円)", m.group(0))
        if amount:
            mul = {"億円": 10000, "万円": 1, "千円": 0.1, "円": 0.0001}[amount.group(2)]
            return round(float(amount.group(1)) * mul, 1)
    return None


def extract_project(html: str, url: str, context: dict) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    root = _main(soup)
    for tag in root.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    title_el = root.find("h1") or soup.find("title")
    title = " ".join(title_el.stripped_strings).strip() if title_el else context.get("candidateTitle") or "名称未確認"
    text = " ".join(root.stripped_strings)
    clean = clean_project_description(text)
    notice = _near(clean, ("公示日", "公告日", "掲載日", "募集開始"))
    deadline = _near(clean, ("企画提案書.{0,15}提出期限", "提案書.{0,15}提出期限", "参加申込.{0,15}期限", "応募.{0,10}期限", "提出期限", "締切"))
    presentation = _near(clean, ("プレゼンテーション", "プレゼン", "ヒアリング", "審査会"))
    fit = classify_project(title, clean)
    attachments = []
    for a in root.find_all("a", href=True):
        href = urljoin(url, a["href"])
        label = " ".join(a.stripped_strings).strip()
        if re.search(r"\.(pdf|docx?|xlsx?)($|\?)", href, re.I):
            attachments.append({"name": label or "添付資料", "url": href})
    checked = date.today().isoformat()
    ext = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return {
        "id": f"direct-{ext}", "municipalityCode": context.get("municipalityCode"),
        "area": context.get("area"), "region": context.get("region"), "municipality": context.get("municipality"),
        "organization": context.get("organization") or context.get("municipality"), "title": title,
        "summary": clean[:1800], "noticeDate": notice, "deadline": deadline, "presentationDate": presentation,
        "openingDate": None, "budget": _budget(clean), "status": "open", "sourceSystem": "municipality_direct",
        "sourceUrl": url, "officialSourceUrl": url, "lastChecked": checked, "dataQuality": "official",
        "theme": _themes(title, clean), "dentsuFitScore": fit["score"], "dentsuFitLevel": fit["level"],
        "dentsuCategories": fit["categories"], "dentsuCategoryLabels": fit["category_labels"],
        "dentsuSignals": fit["signals"], "classificationVersion": 2, "attachments": attachments,
    }
