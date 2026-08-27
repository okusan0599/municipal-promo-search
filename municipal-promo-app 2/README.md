# 自治体プロモーション公示検索 v4 Stable

官公需情報ポータルサイト検索APIを使い、全国の広報・観光・SNS・動画・Web・イベント・ブランディング等の役務案件を横断検索するFastAPIアプリです。

## v4で変えた点

Render Freeで503と再起動が繰り返される問題を避けるため、Webサーバー起動時の自動同期・常駐スケジューラーを廃止しました。

- 起動時に外部APIへアクセスしない
- 1回の同期はKKJ API 1リクエストだけ
- 取得上限は初期値120件（最大250件）
- `/health` はGET/HEADとも200
- 初回表示時、キャッシュが空/古い場合だけ同期
- 6時間ごとのGitHub Actions更新にも対応
- JSON書き込みは原子的に更新

## Render設定

Root Directoryは既存の配置に合わせてください（例: `municipal-promo-app 2`）。

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment Variables:

```text
PYTHON_VERSION=3.12.10
KKJ_COUNT_PER_QUERY=120
KKJ_LOOKBACK_DAYS=180
KKJ_CACHE_MINUTES=30
KKJ_TIMEOUT=25
REFRESH_TOKEN=<任意の長いランダム文字列>
```

`AUTO_REFRESH` は不要です。残っていてもv4では起動時同期に使いません。

Renderの Settings > Health Checks を使う場合は、Health Check Pathを次にします。

```text
/health
```

## URL

検索画面:

```text
https://municipal-promo-search.onrender.com/
```

案件JSON:

```text
https://municipal-promo-search.onrender.com/api/projects
```

状態:

```text
https://municipal-promo-search.onrender.com/api/status
```

稼働確認:

```text
https://municipal-promo-search.onrender.com/health
```

## GitHub Actionsによる更新

`.github/workflows/keep-fresh.yml` を利用する場合、Repository secretsに以下を設定します。

- `RENDER_APP_URL` = `https://municipal-promo-search.onrender.com`
- `REFRESH_TOKEN` = Renderと同じ値

6時間ごとにアプリを起こして、1回の軽量同期を行います。

## 注意

官公需情報ポータルは発注機関の全公告を保証するものではありません。表示された案件も、期限・予算・参加条件は必ず「原公示を見る」から自治体等の原文を確認してください。
