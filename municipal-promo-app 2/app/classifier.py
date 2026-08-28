from __future__ import annotations

import re
import unicodedata
from typing import Any

CATEGORY_LABELS: dict[str, str] = {
    "consulting_strategy": "コンサル・戦略策定",
    "pr_communications": "広報・PR・コミュニケーション",
    "advertising_creative": "広告・クリエイティブ",
    "digital_social": "SNS・デジタルマーケティング",
    "content_media": "メディア・コンテンツ・動画",
    "events_experience": "イベント・体験設計",
    "tourism_place_branding": "観光・地域ブランディング",
    "research_marketing": "調査・マーケティング",
    "web_app_service": "Web・アプリ・デジタルサービス",
    "ai_data_dx": "AI・データ活用・DX",
    "branding_identity": "ブランディング・VI/CI",
}

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "consulting_strategy": (
        "コンサル", "コンサルティング", "戦略策定", "事業戦略", "広報戦略", "基本構想",
        "基本計画", "構想策定", "計画策定", "伴走支援", "事業設計", "政策立案",
    ),
    "pr_communications": (
        "広報", "pr", "パブリシティ", "コミュニケーション", "情報発信", "魅力発信",
        "メディアリレーション", "広報戦略", "記者発表", "プロモーション",
    ),
    "advertising_creative": (
        "広告", "広告運用", "クリエイティブ", "キャンペーン", "メディアプラン", "媒体",
        "コピー", "グラフィック", "プロモーション",
    ),
    "digital_social": (
        "sns", "ソーシャルメディア", "instagram", "tiktok", "youtube", "デジタルマーケティング",
        "web広告", "インターネット広告", "リスティング", "運用型広告", "インフルエンサー",
    ),
    "content_media": (
        "動画", "映像", "コンテンツ", "番組", "記事制作", "冊子", "パンフレット", "ポスター",
        "メディア", "撮影", "編集", "ライブ配信",
    ),
    "events_experience": (
        "イベント", "催事", "フェア", "展示会", "式典", "シンポジウム", "セミナー",
        "体験", "運営事務局", "企画運営", "会場運営",
    ),
    "tourism_place_branding": (
        "観光", "誘客", "インバウンド", "地域創生", "地方創生", "地域ブランディング",
        "シティプロモーション", "関係人口", "移住促進", "周遊", "交流人口", "地域活性化",
    ),
    # Generic "調査・分析" is intentionally excluded. Agency fit requires a
    # market/consumer/brand/communications context rather than any research work.
    "research_marketing": (
        "市場調査", "マーケティング調査", "消費者調査", "顧客調査", "ブランド調査", "広告効果測定",
        "広報効果測定", "ニーズ調査", "意識調査", "マーケティング", "アンケート調査",
    ),
    "web_app_service": (
        "webサイト", "ウェブサイト", "ホームページ", "サイト構築", "サイト制作", "アプリ",
        "ポータルサイト", "デジタルサービス", "ui", "ux", "cms", "web制作",
    ),
    "ai_data_dx": (
        "生成ai", "人工知能", "ai", "データ活用", "データ分析", "dx", "デジタル活用",
        "機械学習", "chatgpt", "llm", "実証実験", "実証事業", "データ連携",
    ),
    "branding_identity": (
        "ブランディング", "ブランド戦略", "ブランド", "vi", "ci", "ロゴ", "ネーミング",
        "ブランドガイドライン", "アイデンティティ",
    ),
}

# Description-only matches are intentionally stricter than title matches. These
# phrases are specific enough to represent the scope of work rather than a
# municipality site's navigation/footer text.
BODY_SPECIFIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "consulting_strategy": (
        "コンサルティング", "戦略策定", "事業戦略", "広報戦略", "構想策定", "計画策定", "伴走支援",
    ),
    "pr_communications": (
        "広報戦略", "情報発信", "魅力発信", "メディアリレーション", "パブリシティ", "プロモーション",
    ),
    "advertising_creative": (
        "広告運用", "広告制作", "メディアプラン", "クリエイティブ制作", "キャンペーン企画",
    ),
    "digital_social": (
        "sns運用", "ソーシャルメディア運用", "デジタルマーケティング", "web広告", "インターネット広告",
        "リスティング", "運用型広告", "インフルエンサー",
    ),
    "content_media": (
        "動画制作", "映像制作", "コンテンツ制作", "記事制作", "パンフレット制作", "ポスター制作",
        "撮影・編集", "ライブ配信",
    ),
    "events_experience": (
        "イベント企画", "イベント運営", "展示会運営", "シンポジウム運営", "企画運営", "会場運営",
    ),
    "tourism_place_branding": (
        "観光誘客", "観光プロモーション", "インバウンド", "周遊促進", "地域ブランディング",
        "シティプロモーション", "移住促進", "関係人口創出",
    ),
    "research_marketing": (
        "市場調査", "マーケティング調査", "消費者調査", "顧客調査", "ブランド調査", "広告効果測定",
        "広報効果測定", "ニーズ調査", "意識調査", "アンケート調査",
    ),
    "web_app_service": (
        "サイト構築", "サイト制作", "web制作", "ウェブサイト制作", "ホームページ制作", "サイトリニューアル",
        "webサイトリニューアル", "cms構築", "アプリ開発",
    ),
    "ai_data_dx": (
        "生成ai", "人工知能", "ai活用", "データ活用", "dx推進", "機械学習", "chatgpt", "llm",
        "データ連携", "実証事業",
    ),
    "branding_identity": (
        "ブランディング", "ブランド戦略", "地域ブランディング", "ロゴ制作", "ネーミング", "vi策定", "ci策定",
    ),
}

STRONG_TERMS: tuple[str, ...] = (
    "戦略策定", "コンサルティング", "プロモーション", "コミュニケーション", "広報戦略",
    "ブランディング", "マーケティング", "生成ai", "人工知能", "データ活用", "デジタルマーケティング",
    "広報", "pr", "広告", "sns", "動画", "イベント", "観光", "ai", "dx",
)

PROPOSAL_TERMS: tuple[str, ...] = (
    "企画提案", "プロポーザル", "提案競技", "公募型", "業務委託", "伴走支援", "戦略", "実証",
)

NEGATIVE_TERMS: tuple[tuple[str, int], ...] = (
    ("道路工事", 45), ("舗装工事", 45), ("建築工事", 45), ("土木工事", 45),
    ("改修工事", 35), ("電気工事", 40), ("管工事", 40), ("設備保守", 35),
    ("保守点検", 30), ("清掃", 35), ("警備", 35), ("給食", 40), ("食材", 35),
    ("物品購入", 35), ("資材調達", 35), ("備品購入", 35), ("車両購入", 40),
    ("廃棄物", 35), ("除雪", 40), ("修繕工事", 40),
    ("物流", 25), ("輸送", 25), ("倉庫", 20),
)

BOILERPLATE_MARKERS: tuple[str, ...] = (
    "var publish", "window.navigator", "navigator.useragent", "document.getelementbyid",
    "サイト内検索", "本文へ移動", "メニューを開く", "javascript:",
)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", " ", value).strip()


def _contains(text: str, keyword: str) -> bool:
    needle = _normalize(keyword)
    if re.fullmatch(r"[a-z0-9]+", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text) is not None
    return needle in text


def clean_project_description(text: str) -> str:
    """Remove obvious website shell/script noise while preserving display casing."""
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", text or "", flags=re.I | re.S)
    compacted = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()
    search_text = compacted.lower()
    cut_positions = [search_text.find(marker) for marker in BOILERPLATE_MARKERS if search_text.find(marker) >= 0]
    if cut_positions:
        compacted = compacted[: min(cut_positions)]
    return compacted.strip()[:2400]


def _dedupe_signals(signals: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for signal in signals:
        key = _normalize(signal)
        if key in seen:
            continue
        seen.add(key)
        output.append(signal)
        if len(output) >= 8:
            break
    return output


def classify_project(title: str, description: str = "") -> dict[str, Any]:
    title_text = _normalize(title)
    body_text = clean_project_description(description)
    categories: list[str] = []
    signals: list[str] = []
    score = 0

    for category, title_keywords in CATEGORY_KEYWORDS.items():
        title_matches = [keyword for keyword in title_keywords if _contains(title_text, keyword)]
        body_matches = [
            keyword for keyword in BODY_SPECIFIC_KEYWORDS.get(category, ())
            if _contains(body_text, keyword)
        ]
        if not title_matches and not body_matches:
            continue
        categories.append(category)
        # Title evidence is strongest; body evidence must already be specific.
        score += 26 if title_matches else 18
        signals.extend((title_matches or body_matches)[:2])

    # Strong-term bonus uses the title plus only the cleaned body, so navigation
    # and JavaScript cannot inflate relevance.
    combined = f"{title_text} {body_text}".strip()
    strong_matches = [term for term in STRONG_TERMS if _contains(combined, term)]
    score += min(45, 15 * len(strong_matches))
    signals.extend(strong_matches[:3])

    if any(_contains(combined, term) for term in PROPOSAL_TERMS):
        score += 12
        proposal_signal = next(term for term in PROPOSAL_TERMS if _contains(combined, term))
        signals.append(proposal_signal)

    for term, penalty in NEGATIVE_TERMS:
        if _contains(combined, term):
            score -= penalty
            signals.append(f"除外:{term}")

    score = max(0, min(100, int(score)))
    level = "high" if score >= 70 else "medium" if score >= 45 else "low"

    return {
        "score": score,
        "level": level,
        "categories": categories,
        "category_labels": [CATEGORY_LABELS[category] for category in categories],
        "signals": _dedupe_signals(signals),
    }


def classify_dentsu_fit(text: str) -> dict[str, Any]:
    """Backward-compatible single-text classifier used by existing callers/tests."""
    return classify_project(text, "")
