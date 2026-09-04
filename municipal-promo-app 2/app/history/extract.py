from __future__ import annotations

import hashlib
import io
import re
from datetime import date
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.classifier import classify_project, clean_project_description

ERA_BASE = {"令和": 2018, "平成": 1988}
TITLE_LABELS = ("業務名", "件名", "案件名", "委託業務名", "事業名", "名称", "調達件名")
VENDOR_LABELS = (
    "受託候補者", "受託者", "委託先", "契約相手方", "契約者", "落札者", "落札業者",
    "選定事業者", "選定業者", "優先交渉権者", "最優秀提案者", "受注者", "採択事業者",
)
AMOUNT_LABELS = ("契約金額", "落札金額", "契約額", "決定金額", "委託金額", "落札価格")
DATE_LABELS = ("契約日", "落札日", "開札日", "決定日", "選定日", "審査日", "公表日")


def _compact(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _jp_date(text: str | None) -> str | None:
    text = (text or "").replace("元年", "1年")
    patterns = (
        r"(?P<era>令和|平成)\s*(?P<ey>\d{1,2})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日",
        r"(?P<y>20\d{2})\s*[年/.-]\s*(?P<m>\d{1,2})\s*[月/.-]\s*(?P<d>\d{1,2})\s*日?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        g = match.groupdict()
        year = int(g["y"]) if g.get("y") else ERA_BASE[g["era"]] + int(g["ey"])
        try:
            return date(year, int(g["m"]), int(g["d"])).isoformat()
        except ValueError:
            continue
    return None


def _fiscal_year(text: str | None) -> int | None:
    text = (text or "").replace("元年度", "1年度")
    m = re.search(r"(令和|平成)\s*(\d{1,2})\s*年度", text)
    if m:
        return ERA_BASE[m.group(1)] + int(m.group(2))
    m = re.search(r"\b(20\d{2})\s*年度", text)
    if m:
        return int(m.group(1))
    day = _jp_date(text)
    return int(day[:4]) if day else None


def _amount_man_yen(text: str | None) -> float | None:
    normalized = (text or "").replace(",", "").replace("，", "")
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(億円|万円|千円|円)", normalized)
    if not m:
        return None
    mul = {"億円": 10000, "万円": 1, "千円": 0.1, "円": 0.0001}[m.group(2)]
    return round(float(m.group(1)) * mul, 1)


def _clean_vendor(value: str | None) -> str | None:
    value = _compact(value)
    if not value or len(value) > 180:
        return None
    value = re.split(r"(?:契約金額|落札金額|契約日|決定日|選定日|所在地|住所)\s*[:：]?", value, maxsplit=1)[0].strip(" ：:／/")
    if value in {"なし", "該当なし", "不調", "中止", "未定", "非公表"}:
        return value
    return value or None


def _value_for(pairs: list[tuple[str, str]], labels: Iterable[str]) -> str | None:
    for label, value in pairs:
        norm = _compact(label)
        if any(x in norm for x in labels):
            return _compact(value)
    return None


def _pairs_from_dom(root) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for tr in root.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) == 2:
            pairs.append((_compact(cells[0].get_text(" ", strip=True)), _compact(cells[1].get_text(" ", strip=True))))
        elif len(cells) > 2 and cells[0].name == "th":
            pairs.append((_compact(cells[0].get_text(" ", strip=True)), _compact(" ".join(c.get_text(" ", strip=True) for c in cells[1:]))))
    for dt in root.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            pairs.append((_compact(dt.get_text(" ", strip=True)), _compact(dd.get_text(" ", strip=True))))
    return pairs


def _table_records(root) -> list[dict]:
    records = []
    for table in root.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers = [_compact(c.get_text(" ", strip=True)) for c in header_cells]
        title_idx = next((i for i, h in enumerate(headers) if any(k in h for k in TITLE_LABELS)), None)
        vendor_idx = next((i for i, h in enumerate(headers) if any(k in h for k in VENDOR_LABELS)), None)
        amount_idx = next((i for i, h in enumerate(headers) if any(k in h for k in AMOUNT_LABELS)), None)
        date_idx = next((i for i, h in enumerate(headers) if any(k in h for k in DATE_LABELS)), None)
        if title_idx is None or vendor_idx is None:
            continue
        for tr in rows[1:]:
            cells = tr.find_all(["th", "td"])
            values = [_compact(c.get_text(" ", strip=True)) for c in cells]
            if max(title_idx, vendor_idx) >= len(values):
                continue
            title = values[title_idx]
            vendor = _clean_vendor(values[vendor_idx])
            if not title or not vendor:
                continue
            records.append({
                "title": title,
                "vendor": vendor,
                "amount": _amount_man_yen(values[amount_idx]) if amount_idx is not None and amount_idx < len(values) else None,
                "awardDate": _jp_date(values[date_idx]) if date_idx is not None and date_idx < len(values) else None,
                "raw": " | ".join(values),
            })
    return records


def _text_value_after_labels(text: str, labels: Iterable[str], stop_labels: Iterable[str], max_len: int = 180) -> str | None:
    label_group = "|".join(re.escape(x) for x in labels)
    stop_group = "|".join(re.escape(x) for x in stop_labels)
    pattern = rf"(?:{label_group})\s*[:：]?\s*(.{{1,{max_len}}}?)(?=\s*(?:{stop_group})\s*[:：]?|$)"
    m = re.search(pattern, text)
    return _compact(m.group(1)) if m else None


def _fallback_record(root, page_title: str, full_text: str) -> dict | None:
    pairs = _pairs_from_dom(root)
    title = _value_for(pairs, TITLE_LABELS)
    vendor = _clean_vendor(_value_for(pairs, VENDOR_LABELS))
    amount_text = _value_for(pairs, AMOUNT_LABELS)
    date_text = _value_for(pairs, DATE_LABELS)
    all_labels = (*TITLE_LABELS, *VENDOR_LABELS, *AMOUNT_LABELS, *DATE_LABELS, "所在地", "住所", "担当課", "評価点", "審査結果")
    if not title:
        title = _text_value_after_labels(full_text, TITLE_LABELS, tuple(x for x in all_labels if x not in TITLE_LABELS), max_len=220)
    if not vendor:
        vendor = _clean_vendor(_text_value_after_labels(full_text, VENDOR_LABELS, tuple(x for x in all_labels if x not in VENDOR_LABELS), max_len=160))
    if not amount_text:
        amount_text = _text_value_after_labels(full_text, AMOUNT_LABELS, tuple(x for x in all_labels if x not in AMOUNT_LABELS), max_len=80)
    if not date_text:
        date_text = _text_value_after_labels(full_text, DATE_LABELS, tuple(x for x in all_labels if x not in DATE_LABELS), max_len=80)
    if not title:
        title = page_title
    if not vendor or not title:
        return None
    return {
        "title": title,
        "vendor": vendor,
        "amount": _amount_man_yen(amount_text),
        "awardDate": _jp_date(date_text),
        "raw": full_text[:1400],
    }


def _finalize(records: list[dict], url: str, context: dict, page_title: str, full_text: str) -> list[dict]:
    output = []
    seen = set()
    page_year = _fiscal_year(page_title) or _fiscal_year(full_text[:1200]) or _fiscal_year(url)
    for record in records:
        title = clean_project_description(record.get("title") or "")[:500]
        vendor = _clean_vendor(record.get("vendor"))
        if not title or not vendor:
            continue
        award_date = record.get("awardDate") or _jp_date(record.get("raw"))
        year = _fiscal_year(record.get("raw")) or _fiscal_year(title) or page_year
        if year is None and award_date:
            year = int(award_date[:4])
        if year is None:
            continue
        fit = classify_project(title, "")
        key = (title, vendor, year)
        if key in seen:
            continue
        seen.add(key)
        digest = hashlib.sha256(f"{context.get('municipalityCode')}|{title}|{vendor}|{year}|{url}".encode("utf-8")).hexdigest()[:24]
        output.append({
            "id": f"award-{digest}",
            "municipalityCode": context.get("municipalityCode"),
            "area": context.get("area"), "region": context.get("region"),
            "municipality": context.get("municipality"), "organization": context.get("organization") or context.get("municipality"),
            "title": title, "vendor": vendor, "amount": record.get("amount"),
            "awardDate": award_date, "year": year,
            "sourceUrl": url, "sourceSystem": "municipality_result", "dataQuality": "official_result",
            "dentsuCategories": fit["categories"], "dentsuCategoryLabels": fit["category_labels"],
        })
    return output


def extract_history_records(html: str, url: str, context: dict) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    root = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in root.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    page_title_el = root.find("h1") or soup.find("title")
    page_title = _compact(page_title_el.get_text(" ", strip=True) if page_title_el else context.get("candidateTitle") or "")
    text = clean_project_description(_compact(root.get_text(" ", strip=True)))
    records = _table_records(root)
    if not records:
        fallback = _fallback_record(root, page_title, text)
        if fallback:
            records = [fallback]
    return _finalize(records, url, context, page_title, text)


def extract_history_records_from_pdf(content: bytes, url: str, context: dict, max_pages: int = 20) -> list[dict]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:max_pages])
    except Exception:
        return []
    cleaned = clean_project_description(_compact(text))
    if not cleaned:
        return []
    # The fallback parser operates on extracted text, so a minimal empty DOM is sufficient.
    soup = BeautifulSoup("<main></main>", "html.parser")
    root = soup.main
    fallback = _fallback_record(root, context.get("candidateTitle") or "", cleaned)
    records = [fallback] if fallback else []
    return _finalize(records, url, context, context.get("candidateTitle") or "", cleaned)


def extract_result_document_links(html: str, base_url: str, limit: int = 8) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#", 1)[0]
        label = _compact(a.get_text(" ", strip=True))
        if href in seen or not re.search(r"\.pdf($|\?)", href, re.I):
            continue
        low = f"{label} {href}".lower()
        if not re.search(r"結果|落札|契約|選定|審査|受託|候補|kekka|result|award", low, re.I):
            continue
        rows.append({"url": href, "title": label or href})
        seen.add(href)
    return rows[:limit]
