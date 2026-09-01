from pathlib import Path

HTML = Path("index.html").read_text(encoding="utf-8")


def test_default_fit_filter_is_medium_plus():
    assert 'id="fitLevel"' in HTML
    assert '<option value="medium+" selected>' in HTML


def test_category_filter_contract_exists():
    assert 'data-dentsu-category=' in HTML
    assert 'dentsuCategories' in HTML


def test_all_dentsu_category_ids_are_present():
    for category in [
        "consulting_strategy", "pr_communications", "advertising_creative",
        "digital_social", "content_media", "events_experience",
        "tourism_place_branding", "research_marketing", "web_app_service",
        "ai_data_dx", "branding_identity",
    ]:
        assert f'data-dentsu-category="{category}"' in HTML


def test_v6_ui_distinguishes_direct_official_sources():
    assert 'municipality_direct' in HTML
    assert '自治体公式サイト（直接収集）' in HTML
    assert 'officialSourceUrl' in HTML
    assert 'sourceCount' in HTML
