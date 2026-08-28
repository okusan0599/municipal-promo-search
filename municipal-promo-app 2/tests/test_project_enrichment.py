from app.kkj import _parse_xml


def test_parse_xml_adds_dentsu_fit_fields():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
    <Root>
      <SearchHits>1</SearchHits>
      <SearchResults>
        <SearchResult>
          <Key>abc-1</Key>
          <ExternalDocumentURI>https://example.test/notice</ExternalDocumentURI>
          <ProjectName>生成AIを活用した広報戦略策定業務</ProjectName>
          <PrefectureName>東京都</PrefectureName>
          <CityName>千代田区</CityName>
          <OrganizationName>千代田区</OrganizationName>
          <ProjectDescription>生成AIを活用した広報コミュニケーション戦略の企画提案業務委託</ProjectDescription>
          <CftIssueDate>2026-08-20</CftIssueDate>
        </SearchResult>
      </SearchResults>
    </Root>'''
    hits, projects = _parse_xml(xml)
    assert hits == 1
    assert len(projects) == 1
    project = projects[0]
    assert project["dentsuFitLevel"] == "high"
    assert project["dentsuFitScore"] >= 70
    assert "ai_data_dx" in project["dentsuCategories"]
    assert "pr_communications" in project["dentsuCategories"]
    assert "dentsuCategoryLabels" in project
    assert "dentsuSignals" in project


def test_cached_legacy_project_is_enriched_without_upstream_refresh(monkeypatch, tmp_path):
    import json
    import app.kkj as kkj

    cache = tmp_path / "projects.json"
    status = tmp_path / "status.json"
    cache.write_text(json.dumps([{
        "id": "legacy-1",
        "title": "生成AIを活用した広報戦略策定業務",
        "summary": "コミュニケーション戦略とプロモーションの企画提案",
        "sourceUrl": "https://example.test/legacy",
    }], ensure_ascii=False), encoding="utf-8")
    status.write_text(json.dumps({"state": "completed", "updated_at": "2099-01-01T00:00:00+09:00"}), encoding="utf-8")

    monkeypatch.setattr(kkj, "CACHE_FILE", cache)
    monkeypatch.setattr(kkj, "STATUS_FILE", status)

    rows = kkj.get_projects(refresh_if_stale=False)
    assert rows[0]["dentsuFitLevel"] == "high"
    assert "pr_communications" in rows[0]["dentsuCategories"]


def test_logistics_page_shell_does_not_gain_tourism_or_web_tags():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
    <Root>
      <SearchHits>1</SearchHits>
      <SearchResults>
        <SearchResult>
          <Key>logistics-1</Key>
          <ExternalDocumentURI>https://example.test/logistics</ExternalDocumentURI>
          <ProjectName>京都府北部地域の物流課題の解決に向けた調査・分析業務委託に係る総合評価競争入札の実施について</ProjectName>
          <PrefectureName>京都府</PrefectureName>
          <CityName>京都府</CityName>
          <OrganizationName>京都府</OrganizationName>
          <ProjectDescription>京都府北部地域の物流課題の解決に向けた調査・分析業務委託について。京都府ホームページ var publish = true; var userAgent = window.navigator.userAgent; 観光・広報・SNS・Web制作などのサイトナビゲーション</ProjectDescription>
          <CftIssueDate>2026-08-21</CftIssueDate>
        </SearchResult>
      </SearchResults>
    </Root>'''
    _, projects = _parse_xml(xml)
    project = projects[0]
    assert "観光PR" not in project["theme"]
    assert "Web制作" not in project["theme"]
    assert "tourism_place_branding" not in project["dentsuCategories"]
    assert "web_app_service" not in project["dentsuCategories"]
    assert project["dentsuFitLevel"] == "low"


def test_real_tourism_title_keeps_tourism_classification_even_with_page_shell():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
    <Root>
      <SearchHits>1</SearchHits>
      <SearchResults>
        <SearchResult>
          <Key>tourism-1</Key>
          <ExternalDocumentURI>https://example.test/tourism</ExternalDocumentURI>
          <ProjectName>インバウンド観光誘客プロモーション業務委託</ProjectName>
          <PrefectureName>福岡県</PrefectureName>
          <CityName>福岡市</CityName>
          <OrganizationName>福岡市</OrganizationName>
          <ProjectDescription>海外市場向けの情報発信、広告及び動画制作を行う。福岡市ホームページ var publish = true;</ProjectDescription>
          <CftIssueDate>2026-08-21</CftIssueDate>
        </SearchResult>
      </SearchResults>
    </Root>'''
    _, projects = _parse_xml(xml)
    project = projects[0]
    assert "観光PR" in project["theme"]
    assert "tourism_place_branding" in project["dentsuCategories"]
    assert project["dentsuFitLevel"] in {"medium", "high"}


def test_cached_project_reclassifies_when_classifier_version_is_old(monkeypatch, tmp_path):
    import json
    import app.kkj as kkj

    cache = tmp_path / "projects.json"
    status = tmp_path / "status.json"
    cache.write_text(json.dumps([{
        "id": "legacy-logistics",
        "title": "物流課題の解決に向けた調査・分析業務委託",
        "summary": "京都府ホームページ var publish = true; 観光・広報・Web制作",
        "theme": ["観光PR", "広報・広告", "Web制作"],
        "dentsuFitScore": 88,
        "dentsuFitLevel": "high",
        "dentsuCategories": ["tourism_place_branding", "web_app_service"],
        "dentsuCategoryLabels": ["観光・地域ブランディング", "Web・アプリ・デジタルサービス"],
        "dentsuSignals": ["観光", "ホームページ"],
        "classificationVersion": 1,
        "sourceUrl": "https://example.test/legacy-logistics"
    }], ensure_ascii=False), encoding="utf-8")
    status.write_text(json.dumps({"state": "completed", "updated_at": "2099-01-01T00:00:00+09:00"}), encoding="utf-8")

    monkeypatch.setattr(kkj, "CACHE_FILE", cache)
    monkeypatch.setattr(kkj, "STATUS_FILE", status)

    rows = kkj.get_projects(refresh_if_stale=False)
    row = rows[0]
    assert row["classificationVersion"] >= 2
    assert "観光PR" not in row["theme"]
    assert "tourism_place_branding" not in row["dentsuCategories"]
    assert row["dentsuFitLevel"] == "low"
