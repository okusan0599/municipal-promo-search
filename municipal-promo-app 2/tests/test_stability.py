import os
from fastapi.testclient import TestClient


def test_health_supports_head():
    from app.main import app
    with TestClient(app) as client:
        response = client.head('/health')
    assert response.status_code == 200


def test_startup_does_not_launch_background_threads(monkeypatch):
    import app.main as main
    created = []

    class FakeThread:
        def __init__(self, *args, **kwargs):
            created.append((args, kwargs))
        def start(self):
            pass

    monkeypatch.setattr(main.threading, 'Thread', FakeThread)
    monkeypatch.setenv('AUTO_REFRESH', 'true')
    main.startup()
    assert created == []


def test_refresh_performs_single_upstream_request(monkeypatch, tmp_path):
    import app.kkj as kkj

    monkeypatch.setattr(kkj, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(kkj, 'CACHE_FILE', tmp_path / 'projects.json')
    monkeypatch.setattr(kkj, 'STATUS_FILE', tmp_path / 'status.json')
    monkeypatch.setattr(kkj, 'KKJ_REQUEST_INTERVAL', 0)

    calls = []

    def fake_fetch(query, issue_from):
        calls.append((query, issue_from))
        return 1, [{
            'id': 'x', 'sourceUrl': 'https://example.test/x', 'status': 'open',
            'deadline': '2099-01-01', 'noticeDate': '2026-08-01'
        }]

    monkeypatch.setattr(kkj, '_fetch_group', fake_fetch)
    kkj.refresh_projects(force=True)
    assert len(calls) == 1


def test_projects_endpoint_refreshes_with_one_request(monkeypatch, tmp_path):
    import app.kkj as kkj
    import app.main as main

    monkeypatch.setattr(kkj, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(kkj, 'CACHE_FILE', tmp_path / 'projects.json')
    monkeypatch.setattr(kkj, 'STATUS_FILE', tmp_path / 'status.json')

    def fake_fetch(query, issue_from):
        return 1, [{
            'id': 'x', 'sourceUrl': 'https://example.test/x', 'status': 'open',
            'deadline': '2099-01-01', 'noticeDate': '2026-08-01',
            'area': '九州', 'region': '福岡県', 'municipality': '福岡市',
            'organization': '福岡市', 'title': '観光プロモーション業務',
            'summary': 'テスト', 'theme': ['観光PR'], 'budget': 1000,
            'dentsuFitScore': 88, 'dentsuFitLevel': 'high',
            'dentsuCategories': ['tourism_place_branding', 'pr_communications'],
            'dentsuCategoryLabels': ['観光・地域ブランディング', '広報・PR・コミュニケーション'],
            'dentsuSignals': ['観光', 'プロモーション'],
            'presentationDate': None, 'openingDate': None, 'lastChecked': '2026-08-27T12:00:00+09:00'
        }]

    monkeypatch.setattr(kkj, '_fetch_group', fake_fetch)
    with TestClient(main.app) as client:
        response = client.get('/api/projects?refresh=true')
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body[0]['title'] == '観光プロモーション業務'
    assert body[0]['dentsuFitLevel'] == 'high'
    assert body[0]['dentsuCategories'] == ['tourism_place_branding', 'pr_communications']
