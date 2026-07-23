from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DIRECTORY_FILE = DATA_DIR / "municipalities.json"
DIRECTORY_STATUS_FILE = DATA_DIR / "directory_status.json"
JLIS_MAP_URL = "https://www.j-lis.go.jp/spd/map-search/cms_1069.html"

HEADERS = {
    "User-Agent": "MunicipalPromotionSearch/2.0 (+public procurement index; low-frequency crawler)",
    "Accept-Language": "ja,en;q=0.8",
}
TIMEOUT = 25

PREFECTURE_AREA = {
    "北海道": "北海道",
    "青森県": "東北", "岩手県": "東北", "宮城県": "東北", "秋田県": "東北", "山形県": "東北", "福島県": "東北",
    "茨城県": "北関東", "栃木県": "北関東", "群馬県": "北関東",
    "埼玉県": "南関東", "千葉県": "南関東", "東京都": "南関東", "神奈川県": "南関東",
    "新潟県": "甲信越", "山梨県": "甲信越", "長野県": "甲信越",
    "富山県": "北陸", "石川県": "北陸", "福井県": "北陸",
    "岐阜県": "東海", "静岡県": "東海", "愛知県": "東海", "三重県": "東海",
    "滋賀県": "近畿", "京都府": "近畿", "大阪府": "近畿", "兵庫県": "近畿", "奈良県": "近畿", "和歌山県": "近畿",
    "鳥取県": "中国", "島根県": "中国", "岡山県": "中国", "広島県": "中国", "山口県": "中国",
    "徳島県": "四国", "香川県": "四国", "愛媛県": "四国", "高知県": "四国",
    "福岡県": "九州", "佐賀県": "九州", "長崎県": "九州", "熊本県": "九州", "大分県": "九州", "宮崎県": "九州", "鹿児島県": "九州",
    "沖縄県": "沖縄",
}
PREFECTURES = set(PREFECTURE_AREA)
EXCLUDE_LABELS = {
    "全国自治体マップ検索", "前のページに戻る", "印刷用ページを表示", "ふくおか電子申請サービス",
}
EXCLUDE_NAME_TERMS = ["広域連合", "一部事務組合", "後期高齢者", "電子申請", "行政手続"]


def fetch(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def clean_name(text: str) -> str:
    return re.sub(r"\s+", "", text).strip()


def is_external_official_link(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return bool(host) and "j-lis.go.jp" not in host and not host.endswith("lg-waps.go.jp")


def directory_is_fresh(days: int = 30) -> bool:
    try:
        status = json.loads(DIRECTORY_STATUS_FILE.read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(status["updated_at"])
        return datetime.now(updated.tzinfo) - updated < timedelta(days=days)
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return False


def build_directory(force: bool = False) -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not force and directory_is_fresh() and DIRECTORY_FILE.exists():
        return json.loads(DIRECTORY_FILE.read_text(encoding="utf-8"))

    top = BeautifulSoup(fetch(JLIS_MAP_URL), "html.parser")
    prefecture_pages: list[tuple[str, str]] = []
    seen_pages: set[str] = set()
    for anchor in top.find_all("a", href=True):
        label = clean_name(anchor.get_text(" ", strip=True))
        if label not in PREFECTURES:
            continue
        url = urljoin(JLIS_MAP_URL, anchor["href"])
        if url in seen_pages:
            continue
        seen_pages.add(url)
        prefecture_pages.append((label, url))

    municipalities: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for prefecture, page_url in prefecture_pages:
        try:
            soup = BeautifulSoup(fetch(page_url), "html.parser")
            h1 = soup.find("h1")
            page_prefecture = clean_name(h1.get_text(" ", strip=True)) if h1 else prefecture
            if page_prefecture in PREFECTURES:
                prefecture = page_prefecture
            for anchor in soup.find_all("a", href=True):
                name = clean_name(anchor.get_text(" ", strip=True))
                url = urljoin(page_url, anchor["href"])
                if not name or name in EXCLUDE_LABELS or any(term in name for term in EXCLUDE_NAME_TERMS):
                    continue
                if not is_external_official_link(url):
                    continue
                # J-LIS pages may list designated-city wards. Keep them because the user requested wards too.
                key = (name, urlparse(url).netloc.lower() + urlparse(url).path.rstrip("/"))
                if key in seen:
                    continue
                seen.add(key)
                municipalities.append({
                    "area": PREFECTURE_AREA[prefecture],
                    "region": prefecture,
                    "municipality": name,
                    "url": url,
                    "source_name": f"{name}公式サイト",
                    "directory_source": page_url,
                })
        except Exception as exc:  # continue across all prefectures
            errors.append({"prefecture": prefecture, "url": page_url, "error": str(exc)})

    municipalities.sort(key=lambda item: (item["region"], item["municipality"]))
    DIRECTORY_FILE.write_text(json.dumps(municipalities, ensure_ascii=False, indent=2), encoding="utf-8")
    DIRECTORY_STATUS_FILE.write_text(json.dumps({
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(municipalities),
        "prefecture_pages": len(prefecture_pages),
        "errors": errors,
        "source": JLIS_MAP_URL,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return municipalities


if __name__ == "__main__":
    print(json.dumps({"count": len(build_directory(force=True))}, ensure_ascii=False))
