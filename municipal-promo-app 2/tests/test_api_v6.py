from fastapi.testclient import TestClient


def _repo(tmp_path):
    from app.db import Database
    from app.repository import ProjectRepository
    db = Database(f"sqlite:///{tmp_path/'api.db'}"); db.create_all(); return ProjectRepository(db)


def test_projects_reads_combined_database_without_direct_crawl(monkeypatch, tmp_path):
    import app.main as main
    repo = _repo(tmp_path)
    repo.upsert_municipality({"code":"412023","prefecture":"佐賀県","name":"唐津市","kind":"city","official_url":"https://www.city.karatsu.lg.jp/","area":"九州","active":True})
    repo.upsert_project({"id":"d1","municipalityCode":"412023","region":"佐賀県","municipality":"唐津市","organization":"唐津市","title":"観光プロモーション業務","summary":"観光誘客","sourceSystem":"municipality_direct","sourceUrl":"https://www.city.karatsu.lg.jp/p/1","officialSourceUrl":"https://www.city.karatsu.lg.jp/p/1","dentsuFitLevel":"high","dentsuFitScore":90,"dentsuCategories":["tourism_place_branding"],"theme":["観光PR"]})
    monkeypatch.setattr(main, "get_repository", lambda: repo)
    monkeypatch.setattr(main, "database_enabled", lambda: True)
    with TestClient(main.app) as client:
        r = client.get('/api/projects?refresh=false')
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["sourceSystem"] == "municipality_direct"
    assert rows[0]["officialSourceUrl"].startswith("https://www.city.karatsu")


def test_admin_coverage_endpoint(monkeypatch, tmp_path):
    import app.main as main
    repo = _repo(tmp_path)
    repo.upsert_municipality({"code":"412023","prefecture":"佐賀県","name":"唐津市","kind":"city","official_url":"https://www.city.karatsu.lg.jp/","area":"九州","active":True})
    repo.upsert_source({"municipality_code":"412023","source_type":"procurement","url":"https://www.city.karatsu.lg.jp/site/nyusatsu/","title":"入札","priority":1,"active":True})
    monkeypatch.setattr(main, "get_repository", lambda: repo)
    monkeypatch.setattr(main, "database_enabled", lambda: True)
    with TestClient(main.app) as client:
        r = client.get('/api/admin/municipality-coverage')
    assert r.status_code == 200
    assert r.json()["municipalitiesWithSources"] == 1


def test_health_reports_storage_mode(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "database_enabled", lambda: True)
    with TestClient(main.app) as client:
        body = client.get('/health').json()
    assert body["storage"] == "postgresql"
