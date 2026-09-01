from datetime import datetime, timezone


def _repo(tmp_path):
    from app.db import Database
    from app.repository import ProjectRepository
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_all()
    return ProjectRepository(db)


def test_municipality_and_source_upsert(tmp_path):
    repo = _repo(tmp_path)
    municipality = repo.upsert_municipality({
        "code": "412023", "prefecture": "佐賀県", "name": "唐津市",
        "kind": "city", "official_url": "https://www.city.karatsu.lg.jp/",
        "area": "九州", "active": True,
    })
    source = repo.upsert_source({
        "municipality_code": "412023", "source_type": "procurement",
        "url": "https://www.city.karatsu.lg.jp/site/nyusatsu/", "title": "入札情報",
        "discovery_method": "seed", "priority": 1, "active": True,
    })
    assert municipality["name"] == "唐津市"
    assert source["municipalityCode"] == "412023"
    assert repo.coverage_stats()["municipalities"] == 1
    assert repo.coverage_stats()["municipalitiesWithSources"] == 1


def test_official_project_wins_over_kkj_for_same_municipality_and_title(tmp_path):
    repo = _repo(tmp_path)
    repo.upsert_municipality({
        "code": "412023", "prefecture": "佐賀県", "name": "唐津市",
        "kind": "city", "official_url": "https://www.city.karatsu.lg.jp/",
        "area": "九州", "active": True,
    })
    base = {
        "municipalityCode": "412023", "region": "佐賀県", "municipality": "唐津市",
        "organization": "唐津市", "title": "観光プロモーション業務",
        "noticeDate": "2026-09-01", "deadline": "2026-09-30", "budget": 10000000,
        "summary": "官公需側", "dentsuFitLevel": "high", "dentsuFitScore": 90,
        "dentsuCategories": ["tourism_place_branding"], "theme": ["観光PR"],
    }
    repo.upsert_project({**base, "id": "kkj-1", "sourceSystem": "kkj", "sourceUrl": "https://kkj.example/1"})
    repo.upsert_project({**base, "id": "direct-1", "summary": "自治体公式本文", "sourceSystem": "municipality_direct",
                         "sourceUrl": "https://www.city.karatsu.lg.jp/notice/1", "officialSourceUrl": "https://www.city.karatsu.lg.jp/notice/1"})
    rows = repo.list_projects()
    assert len(rows) == 1
    assert rows[0]["summary"] == "自治体公式本文"
    assert rows[0]["sourceSystem"] == "municipality_direct"
    assert rows[0]["sourceCount"] == 2


def test_unattempted_municipalities_are_discovered_before_retries(tmp_path):
    repo = _repo(tmp_path)
    for code, name in [("100001","A市"),("100002","B市")]:
        repo.upsert_municipality({"code":code,"prefecture":"群馬県","name":name,"kind":"city","official_url":f"https://{code}.example/","area":"北関東","active":True})
    repo.mark_municipality_verified("100001")
    rows = repo.list_municipalities(without_sources=True, limit=2)
    assert rows[0]["code"] == "100002"


def test_dedupe_matches_kkj_without_municipality_code_to_direct_source(tmp_path):
    repo = _repo(tmp_path)
    common = {"region":"佐賀県","municipality":"唐津市","organization":"唐津市","title":"観光プロモーション業務","deadline":"2026-09-30","dentsuFitLevel":"high","dentsuFitScore":90}
    repo.upsert_project({**common,"id":"k","sourceSystem":"kkj","sourceUrl":"https://kkj.example/k"})
    repo.upsert_project({**common,"id":"d","municipalityCode":"412023","sourceSystem":"municipality_direct","sourceUrl":"https://www.city.karatsu.lg.jp/d","officialSourceUrl":"https://www.city.karatsu.lg.jp/d"})
    rows = repo.list_projects()
    assert len(rows) == 1
    assert rows[0]["sourceCount"] == 2
