
def test_seed_rows_excludes_designated_city_wards_but_keeps_tokyo_special_wards(tmp_path):
    from app.db import Database
    from app.repository import ProjectRepository
    from app.jobs.seed_db import seed_rows
    db = Database(f"sqlite:///{tmp_path/'seed.db'}"); db.create_all(); repo = ProjectRepository(db)
    rows = [
        {"pref":"北海道","city":"札幌市","url":"https://www.city.sapporo.jp/","lgcode":"011002"},
        {"pref":"北海道","city":"札幌市 中央区","url":"https://www.city.sapporo.jp/chuo/","lgcode":"011011"},
        {"pref":"東京都","city":"千代田区","url":"https://www.city.chiyoda.lg.jp/","lgcode":"131016"},
        {"pref":"佐賀県","city":"唐津市","url":"https://www.city.karatsu.lg.jp/","lgcode":"412023"},
    ]
    count = seed_rows(repo, rows, [])
    assert count == 3
    stats = repo.coverage_stats()
    assert stats["municipalities"] == 3


def test_discover_one_municipality_saves_high_scoring_source(tmp_path):
    from app.db import Database
    from app.repository import ProjectRepository
    from app.jobs.discover_sources import discover_for_municipality
    db = Database(f"sqlite:///{tmp_path/'discover.db'}"); db.create_all(); repo = ProjectRepository(db)
    repo.upsert_municipality({"code":"412023","prefecture":"佐賀県","name":"唐津市","kind":"city","official_url":"https://www.city.karatsu.lg.jp/","area":"九州","active":True})
    class FakeClient:
        def fetch(self, url, **kwargs):
            return type("R",(),{"text":'<a href="/site/nyusatsu/">入札・契約情報</a><a href="/life/">くらし</a>'})()
    saved = discover_for_municipality(repo, FakeClient(), {"code":"412023","officialUrl":"https://www.city.karatsu.lg.jp/"})
    assert saved == 1
    assert repo.coverage_stats()["sources"] == 1


def test_crawl_source_failure_does_not_prevent_next_source(tmp_path, monkeypatch):
    from app.db import Database
    from app.repository import ProjectRepository
    from app.jobs.crawl_due_sources import crawl_batch
    db = Database(f"sqlite:///{tmp_path/'crawl.db'}"); db.create_all(); repo = ProjectRepository(db)
    for code, name, url in [("412023","唐津市","https://a.example/"),("402303","糸島市","https://b.example/")]:
        repo.upsert_municipality({"code":code,"prefecture":"佐賀県" if code.startswith('41') else "福岡県","name":name,"kind":"city","official_url":url,"area":"九州","active":True})
        repo.upsert_source({"municipality_code":code,"source_type":"proposal","url":url+"proposal/","title":"プロポーザル","priority":1,"active":True})
    class FakeClient:
        def fetch(self, url, **kwargs):
            if "a.example" in url: raise RuntimeError("boom")
            if url.endswith("proposal/"):
                return type("R",(),{"text":'<main><a href="/p/1">観光プロモーション業務委託公募型プロポーザル</a></main>',"etag":None,"last_modified":None,"content_hash":"x","not_modified":False})()
            return type("R",(),{"text":'<main><h1>観光プロモーション業務委託</h1><p>観光誘客プロモーション。提出期限 令和8年9月30日</p></main>',"etag":None,"last_modified":None,"content_hash":"y","not_modified":False})()
    result = crawl_batch(repo, FakeClient(), limit=10)
    assert result["failed"] == 1
    assert result["succeeded"] == 1
    assert result["projects"] == 1
