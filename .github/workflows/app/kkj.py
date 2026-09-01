from __future__ import annotations

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from .classifier import classify_project, clean_project_description
from .project_status import project_status

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_FILE = DATA_DIR / "kkj_projects.json"
STATUS_FILE = DATA_DIR / "kkj_status.json"
CLASSIFICATION_VERSION = 2

KKJ_API_URL = os.getenv("KKJ_API_URL", "https://www.kkj.go.jp/api/")
KKJ_LOOKBACK_DAYS = int(os.getenv("KKJ_LOOKBACK_DAYS", "180"))
KKJ_CACHE_MINUTES = int(os.getenv("KKJ_CACHE_MINUTES", "30"))
KKJ_COUNT_PER_QUERY = min(250, max(20, int(os.getenv("KKJ_COUNT_PER_QUERY", "120"))))
KKJ_TIMEOUT = int(os.getenv("KKJ_TIMEOUT", "25"))
KKJ_REQUEST_INTERVAL = float(os.getenv("KKJ_REQUEST_INTERVAL", "1.0"))

HEADERS = {
    "User-Agent": "MunicipalPromotionSearch/3.0 (uses Japan SME Agency Kankouju procurement search API)",
    "Accept": "application/xml,text/xml,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.5",
}

# Keep each live sync bounded to one upstream request. This is deliberately
# conservative for Render Free (512 MB): the KKJ API returns full notice text in XML,
# so requesting hundreds of records across multiple query groups can create large
# transient memory spikes.
COMBINED_QUERY = (
    "プロモーション OR シティプロモーション OR 広報 OR 広告 OR ブランディング OR "
    "観光 OR 誘客 OR 移住 OR 関係人口 OR 魅力発信 OR SNS OR 動画 OR 映像 OR Web OR "
    "ホームページ OR イベント OR キャンペーン OR デザイン OR クリエイティブ OR "
    "パンフレット OR ポスター OR ロゴ OR コンサルティング OR 戦略策定 OR 基本構想 OR "
    "事業戦略 OR マーケティング OR 市場調査 OR アンケート OR 調査分析 OR AI OR 生成AI OR "
    "人工知能 OR データ分析 OR データ活用 OR DX OR デジタル活用 OR コミュニケーション OR "
    "広報戦略 OR パブリシティ"
)
QUERY_GROUPS = [COMBINED_QUERY]


AREA_BY_PREF = {
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

THEME_TITLE_RULES = {
    "観光PR": ["観光", "誘客", "周遊", "旅行", "インバウンド"],
    "広報・広告": ["広報", "広告", "PR", "ＰＲ", "情報発信", "魅力発信", "プロモーション"],
    "SNS運用": ["SNS", "ＳＮＳ", "ソーシャル", "Instagram", "TikTok"],
    "動画制作": ["動画", "映像", "YouTube", "ユーチューブ"],
    "Web制作": ["Webサイト", "WEBサイト", "ウェブサイト", "ホームページ制作", "サイト制作", "サイト構築", "リニューアル"],
    "イベント": ["イベント", "催事", "フェア", "展示会", "キャンペーン"],
    "ブランディング": ["ブランド", "ブランディング", "ロゴ", "VI", "CI"],
    "移住・関係人口": ["移住", "交流人口", "関係人口", "定住"],
    "メディア": ["メディア", "テレビ", "ラジオ", "新聞", "雑誌"],
    "制作物": ["パンフレット", "冊子", "ポスター", "リーフレット", "クリエイティブ"],
}

# Description evidence is stricter so a municipality website's menu/footer does
# not create a false theme tag.
THEME_BODY_RULES = {
    "観光PR": ["観光誘客", "観光プロモーション", "インバウンド", "周遊促進", "旅行需要"],
    "広報・広告": ["広報戦略", "広告制作", "広告運用", "情報発信", "魅力発信", "プロモーション"],
    "SNS運用": ["SNS運用", "ソーシャルメディア運用", "Instagram運用", "TikTok運用"],
    "動画制作": ["動画制作", "映像制作", "YouTube動画", "撮影・編集"],
    "Web制作": ["Webサイト制作", "ウェブサイト制作", "ホームページ制作", "サイト構築", "サイト制作", "サイトリニューアル", "CMS構築"],
    "イベント": ["イベント企画", "イベント運営", "展示会運営", "催事運営"],
    "ブランディング": ["ブランド戦略", "地域ブランディング", "ロゴ制作", "VI策定", "CI策定"],
    "移住・関係人口": ["移住促進", "関係人口創出", "交流人口拡大"],
    "メディア": ["メディア露出", "テレビ放映", "ラジオ放送", "新聞広告", "雑誌広告"],
    "制作物": ["パンフレット制作", "冊子制作", "ポスター制作", "リーフレット制作", "クリエイティブ制作"],
}

ERA_BASE = {"令和": 2018, "平成": 1988}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _child_text(node: ET.Element, name: str) -> str:
    for child in list(node):
        if _local(child.tag) == name:
            return _compact("".join(child.itertext()))
    return ""


def _children(node: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(node) if _local(child.tag) == name]


def _iso_day(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    m = re.match(r"(20\d{2})-(\d{2})-(\d{2})", value)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def _parse_japanese_date(text: str) -> str | None:
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
        try:
            return date(year, int(groups["m"]), int(groups["d"])).isoformat()
        except ValueError:
            pass
    return None


def _date_near(text: str, labels: list[str]) -> str | None:
    for label in labels:
        for match in re.finditer(label, text, re.I):
            candidate = _parse_japanese_date(text[match.start(): match.start() + 260])
            if candidate:
                return candidate
    return None


def _extract_deadline(text: str) -> str | None:
    return _date_near(text, [
        r"企画提案書.{0,15}提出期限", r"提案書.{0,15}提出期限", r"企画提案.{0,15}期限",
        r"参加表明.{0,15}期限", r"参加申込.{0,15}期限", r"応募.{0,10}期限",
        r"受付.{0,10}期限", r"提出期限", r"提出締切", r"締切",
    ])


def _extract_presentation(text: str) -> str | None:
    return _date_near(text, [r"プレゼンテーション", r"プレゼン", r"ヒアリング", r"審査会", r"提案審査"])


def _extract_budget(text: str) -> float | None:
    normalized = text.replace(",", "").replace("，", "")
    labels = [
        "予算限度額", "委託上限額", "契約上限額", "委託金額", "提案上限額",
        "予定価格", "限度額", "予算額", "契約限度額", "委託料", "上限額",
    ]
    for label in labels:
        match = re.search(re.escape(label) + r".{0,160}", normalized, re.I)
        if not match:
            continue
        amount = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(億円|万円|千円|円)", match.group(0))
        if amount:
            multiplier = {"億円": 10000, "万円": 1, "千円": 0.1, "円": 0.0001}[amount.group(2)]
            return round(float(amount.group(1)) * multiplier, 1)
    return None


def _themes(title: str, description: str = "") -> list[str]:
    title_low = (title or "").lower()
    body_low = clean_project_description(description).lower()
    found: list[str] = []
    for name, words in THEME_TITLE_RULES.items():
        title_match = any(word.lower() in title_low for word in words)
        body_match = any(word.lower() in body_low for word in THEME_BODY_RULES.get(name, []))
        if title_match or body_match:
            found.append(name)
    return found or ["その他クリエイティブ"]


def _status(deadline: str | None, opening_date: str | None, title: str = "", summary: str = "") -> str:
    return project_status(deadline, opening_date, title=title, summary=summary)


def _attachments(node: ET.Element) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for child in list(node):
        if _local(child.tag) != "Attachments":
            continue
        for attachment in _children(child, "Attachment"):
            name = _child_text(attachment, "Name")
            uri = _child_text(attachment, "Uri")
            if uri:
                result.append({"name": name or "添付資料", "url": uri})
    return result


def _parse_xml(xml_text: str) -> tuple[int, list[dict[str, Any]]]:
    root = ET.fromstring(xml_text)
    for element in root.iter():
        if _local(element.tag) == "Error":
            message = _compact("".join(element.itertext()))
            if message:
                raise RuntimeError(f"KKJ API error: {message}")

    hits = 0
    search_results: ET.Element | None = None
    for element in root.iter():
        name = _local(element.tag)
        if name == "SearchHits":
            try:
                hits = int(_compact("".join(element.itertext())) or "0")
            except ValueError:
                hits = 0
        elif name == "SearchResults":
            search_results = element

    if search_results is None:
        return hits, []

    output: list[dict[str, Any]] = []
    for node in list(search_results):
        if _local(node.tag) != "SearchResult":
            continue
        key = _child_text(node, "Key")
        source_url = _child_text(node, "ExternalDocumentURI")
        title = _child_text(node, "ProjectName") or "名称未確認"
        pref = _child_text(node, "PrefectureName")
        city = _child_text(node, "CityName")
        org = _child_text(node, "OrganizationName")
        description = _child_text(node, "ProjectDescription")
        notice_date = _iso_day(_child_text(node, "CftIssueDate"))
        tender_date = _iso_day(_child_text(node, "TenderSubmissionDeadline"))
        opening_date = _iso_day(_child_text(node, "OpeningTendersEvent"))
        delivery_date = _iso_day(_child_text(node, "PeriodEndTime"))
        deadline = _extract_deadline(description)
        presentation = _extract_presentation(description)
        corpus = f"{title} {description}"
        clean_description = clean_project_description(description)
        budget = _extract_budget(corpus)
        dentsu_fit = classify_project(title, description)
        municipality = city or pref or org
        unique_seed = key or source_url or f"{org}|{title}|{notice_date}"
        project_id = hashlib.sha1(unique_seed.encode("utf-8", errors="ignore")).hexdigest()[:18]
        output.append({
            "id": project_id,
            "area": AREA_BY_PREF.get(pref, ""),
            "region": pref,
            "municipality": municipality,
            "organization": org,
            "noticeDate": notice_date,
            "deadline": deadline,
            "presentationDate": presentation,
            "tenderDate": tender_date,
            "openingDate": opening_date,
            "deliveryDate": delivery_date,
            "budget": budget,
            "theme": _themes(title, description),
            "classificationVersion": CLASSIFICATION_VERSION,
            "dentsuFitScore": dentsu_fit["score"],
            "dentsuFitLevel": dentsu_fit["level"],
            "dentsuCategories": dentsu_fit["categories"],
            "dentsuCategoryLabels": dentsu_fit["category_labels"],
            "dentsuSignals": dentsu_fit["signals"],
            "title": title,
            "summary": _compact(clean_description)[:420],
            "status": _status(deadline, opening_date, title, clean_description),
            "sourceUrl": source_url,
            "sourceName": org or "官公需情報ポータル",
            "sourceSystem": "官公需情報ポータルサイト検索API",
            "lastChecked": datetime.now().astimezone().isoformat(timespec="seconds"),
            "attachments": _attachments(node),
            "category": _child_text(node, "Category"),
            "procedureType": _child_text(node, "ProcedureType"),
            "lgCode": _child_text(node, "LgCode"),
            "cityCode": _child_text(node, "CityCode"),
        })
    return hits, output


def _fetch_group(query: str, issue_from: str) -> tuple[int, list[dict[str, Any]]]:
    params = {
        "Query": query,
        "Category": 3,
        "Count": KKJ_COUNT_PER_QUERY,
        "CFT_Issue_Date": f"{issue_from}/",
    }
    response = SESSION.get(KKJ_API_URL, params=params, timeout=KKJ_TIMEOUT)
    response.raise_for_status()
    # API is documented as UTF-8 XML.
    response.encoding = "utf-8"
    return _parse_xml(response.text)


def refresh_projects(force: bool = False) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_status = _read_json(STATUS_FILE, {})
    if not force and cache_is_fresh():
        return existing_status or {
            "state": "completed",
            "count": len(_read_json(CACHE_FILE, [])),
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    started = datetime.now().astimezone()
    status: dict[str, Any] = {
        "state": "running",
        "started_at": started.isoformat(timespec="seconds"),
        "updated_at": started.isoformat(timespec="seconds"),
        "source": "官公需情報ポータルサイト検索API",
        "query_groups_total": len(QUERY_GROUPS),
        "query_groups_completed": 0,
        "count": len(_read_json(CACHE_FILE, [])),
        "errors": [],
    }
    _write_json(STATUS_FILE, status)

    issue_from = (date.today() - timedelta(days=KKJ_LOOKBACK_DAYS)).isoformat()
    merged: dict[str, dict[str, Any]] = {}
    total_hits = 0

    for idx, query in enumerate(QUERY_GROUPS, start=1):
        status["current_query"] = query
        status["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _write_json(STATUS_FILE, status)
        try:
            hits, rows = _fetch_group(query, issue_from)
            total_hits += hits
            for project in rows:
                # Rows returned by the current fetch pipeline are already classified.
                # Mark them current before caching; this also keeps test/future fetch
                # adapters that provide full classification fields from being
                # needlessly reclassified on the same request.
                if "classificationVersion" not in project and {
                    "dentsuFitScore", "dentsuFitLevel", "dentsuCategories",
                    "dentsuCategoryLabels", "dentsuSignals", "theme",
                }.issubset(project):
                    project["classificationVersion"] = CLASSIFICATION_VERSION
                key = project.get("sourceUrl") or project.get("id")
                if key:
                    merged[key] = project
        except Exception as exc:
            status["errors"].append({"query": query, "error": str(exc)[:500]})
        status["query_groups_completed"] = idx
        status["count"] = len(merged)
        status["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _write_json(STATUS_FILE, status)
        if idx < len(QUERY_GROUPS):
            time.sleep(KKJ_REQUEST_INTERVAL)

    rows = list(merged.values())
    rows.sort(key=lambda p: (p.get("status") == "closed", p.get("deadline") or "9999-12-31", p.get("noticeDate") or "0000-00-00"))

    # Do not erase a useful cache when the upstream API has a temporary failure.
    previous = _read_json(CACHE_FILE, [])
    if rows:
        _write_json(CACHE_FILE, rows)
    elif not previous:
        _write_json(CACHE_FILE, [])

    finished = datetime.now().astimezone()
    status.update({
        "state": "completed" if rows or not status["errors"] else "error",
        "current_query": None,
        "updated_at": finished.isoformat(timespec="seconds"),
        "count": len(rows) if rows else len(previous),
        "raw_hits_sum": total_hits,
        "lookback_days": KKJ_LOOKBACK_DAYS,
        "cache_minutes": KKJ_CACHE_MINUTES,
        "message": "APIから最新候補を取得しました。元公示は各案件リンクで確認してください。" if rows else "APIから新規データを取得できませんでした。キャッシュがあれば継続表示します。",
    })
    _write_json(STATUS_FILE, status)
    return status


def cache_is_fresh() -> bool:
    if not CACHE_FILE.exists() or not STATUS_FILE.exists():
        return False
    status = _read_json(STATUS_FILE, {})
    raw = status.get("updated_at")
    if not raw or status.get("state") not in {"completed", "partial"}:
        return False
    try:
        updated = datetime.fromisoformat(raw)
        return datetime.now(updated.tzinfo) - updated < timedelta(minutes=KKJ_CACHE_MINUTES)
    except Exception:
        return False


def _ensure_dentsu_fields(project: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    required = {
        "dentsuFitScore", "dentsuFitLevel", "dentsuCategories",
        "dentsuCategoryLabels", "dentsuSignals", "theme",
    }
    version = int(project.get("classificationVersion") or 0)
    if version >= CLASSIFICATION_VERSION and required.issubset(project):
        return project, False

    title = str(project.get("title") or "")
    summary = str(project.get("summary") or "")
    fit = classify_project(title, summary)
    enriched = dict(project)
    enriched["dentsuFitScore"] = fit["score"]
    enriched["dentsuFitLevel"] = fit["level"]
    enriched["dentsuCategories"] = fit["categories"]
    enriched["dentsuCategoryLabels"] = fit["category_labels"]
    enriched["dentsuSignals"] = fit["signals"]
    enriched["theme"] = _themes(title, summary)
    enriched["classificationVersion"] = CLASSIFICATION_VERSION
    enriched["summary"] = _compact(clean_project_description(summary))[:420]
    return enriched, True


def get_projects(refresh_if_stale: bool = True) -> list[dict[str, Any]]:
    if refresh_if_stale and not cache_is_fresh():
        refresh_projects(force=True)
    rows = _read_json(CACHE_FILE, [])
    enriched_rows: list[dict[str, Any]] = []
    changed = False
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        enriched, was_changed = _ensure_dentsu_fields(row)
        enriched_rows.append(enriched)
        changed = changed or was_changed
    if changed:
        _write_json(CACHE_FILE, enriched_rows)
    return enriched_rows


def get_status() -> dict[str, Any]:
    return _read_json(STATUS_FILE, {
        "state": "not_started",
        "updated_at": None,
        "count": 0,
        "source": "官公需情報ポータルサイト検索API",
        "errors": [],
    })
