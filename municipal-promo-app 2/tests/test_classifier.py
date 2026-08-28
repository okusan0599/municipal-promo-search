import pytest

from app.classifier import classify_dentsu_fit


def test_pr_ai_strategy_is_high_fit():
    result = classify_dentsu_fit("生成AIを活用した広報コミュニケーション戦略策定及びプロモーション業務委託")
    assert result["level"] == "high"
    assert result["score"] >= 70
    assert "ai_data_dx" in result["categories"]
    assert "pr_communications" in result["categories"]
    assert "consulting_strategy" in result["categories"]


def test_road_construction_is_low_fit():
    result = classify_dentsu_fit("市道舗装改修工事 道路施工及び資材調達")
    assert result["level"] == "low"
    assert result["score"] < 45


@pytest.mark.parametrize("text,category", [
    ("イベント企画運営業務", "events_experience"),
    ("観光地域ブランディング及び誘客プロモーション", "tourism_place_branding"),
    ("市場調査及びマーケティング分析", "research_marketing"),
    ("公式SNSデジタルマーケティング運用", "digital_social"),
    ("Webサイト及びアプリ開発", "web_app_service"),
])
def test_expected_category(text, category):
    assert category in classify_dentsu_fit(text)["categories"]

@pytest.mark.parametrize("text", [
    "広報PR業務委託",
    "イベント企画運営業務委託",
    "SNS運用業務委託",
    "動画制作業務委託",
    "広告制作業務委託",
    "観光誘客業務委託",
    "AI活用業務委託",
])
def test_core_agency_domains_are_visible_in_default_medium_plus(text):
    result = classify_dentsu_fit(text)
    assert result["level"] in {"medium", "high"}
