from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def test_extract_project_links_ignores_archive_and_unrelated_work():
    from app.direct.extract import extract_project_links
    html = (FIX / "karatsu_procurement.html").read_text(encoding="utf-8")
    links = extract_project_links(html, "https://www.city.karatsu.lg.jp/site/nyusatsu/")
    urls = [x["url"] for x in links]
    assert "https://www.city.karatsu.lg.jp/page/12345.html" in urls
    assert not any("archive" in x for x in urls)
    assert not any("road.html" in x for x in urls)


def test_extract_project_reads_main_content_dates_budget_and_attachments():
    from app.direct.extract import extract_project
    html = (FIX / "karatsu_project.html").read_text(encoding="utf-8")
    row = extract_project(html, "https://www.city.karatsu.lg.jp/page/12345.html", {
        "municipalityCode": "412023", "municipality": "唐津市", "region": "佐賀県", "area": "九州"
    })
    assert row["title"].startswith("唐津市観光プロモーション")
    assert row["noticeDate"] == "2026-09-01"
    assert row["deadline"] == "2026-09-30"
    assert row["budget"] == 1200.0
    assert row["sourceSystem"] == "municipality_direct"
    assert row["officialSourceUrl"].endswith("/page/12345.html")
    assert "tourism_place_branding" in row["dentsuCategories"]
    assert row["dentsuFitLevel"] in {"medium", "high"}
    assert row["attachments"][0]["url"].endswith("/files/spec.pdf")


def test_discovery_scores_procurement_links_above_generic_navigation():
    from app.direct.discovery import discover_source_links
    html = '''<html><body><a href="/life/">くらし</a><a href="/site/nyusatsu/">入札・契約情報</a>
    <a href="/proposal/">公募型プロポーザル</a><a href="https://other.example/x">外部</a></body></html>'''
    links = discover_source_links(html, "https://www.example-city.jp/")
    assert links[0]["url"].endswith("/proposal/") or links[0]["url"].endswith("/site/nyusatsu/")
    assert all("other.example" not in x["url"] for x in links)


def test_sitemap_discovery_finds_procurement_paths():
    from app.direct.discovery import discover_sitemap_urls
    xml = '''<?xml version="1.0"?><urlset><url><loc>https://www.example.jp/life/</loc></url><url><loc>https://www.example.jp/site/nyusatsu/</loc></url><url><loc>https://www.example.jp/koubo/proposal/</loc></url></urlset>'''
    rows = discover_sitemap_urls(xml, "https://www.example.jp/")
    urls = [r["url"] for r in rows]
    assert "https://www.example.jp/site/nyusatsu/" in urls
    assert "https://www.example.jp/koubo/proposal/" in urls
    assert "https://www.example.jp/life/" not in urls
