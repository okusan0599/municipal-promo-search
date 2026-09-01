# 自治体プロモーション公示検索 v6

全国自治体の公式公示ページを直接巡回し、官公需情報ポータルの全国横断データと統合して検索するFastAPIアプリです。

## v6の構成

- **Web Service:** 検索UIとAPIのみ。全国クロールは実行しません。
- **PostgreSQL:** 自治体マスター、公示ソース、案件、重複ソースを永続保存します。
- **Cron Job:** `python -m app.jobs.run_cycle` を定期実行し、自治体ソース探索・直接クロール・官公需API更新を行います。
- **自治体マスター:** 初回Cronで `code4fukui/localgovjp` のCC0 JSONから自治体コード・公式トップURLを投入します。政令指定都市の行政区は除外し、東京23特別区は保持します。都道府県庁は別のprefecture JSONから投入します。
- **既知ソース:** `data/source_seed.json`。唐津市の `https://www.city.karatsu.lg.jp/site/nyusatsu/` を初期シードとして同梱しています。

## URL

既存Renderサービスへ上書きする場合、公開URLは従来どおりです。

`https://municipal-promo-search.onrender.com/`

確認API:

- `/health`
- `/api/projects`
- `/api/status`
- `/api/admin/municipality-coverage`
- `/api/admin/source-stats`
- `/api/admin/crawl-status`

## Renderへの反映

### 1. GitHubへv6を上書き

既存リポジトリのRender Root Directory（これまで `municipal-promo-app 2`）へ、このフォルダの中身をアップロードしてCommitします。

### 2. Render Postgresを作成

Render Dashboard → **New → Postgres**

- Name: `municipal-promo-db`
- Region: `Singapore`（Web Serviceと同じ）
- 検証だけならFreeでも可。ただしFree Postgresは30日で期限切れになるため継続運用は有料プラン推奨。

作成後、Postgresの **Internal Database URL** をコピーします。

### 3. Web ServiceにDATABASE_URLを追加

`municipal-promo-search` → **Environment** → Add Environment Variable

- `DATABASE_URL` = PostgresのInternal Database URL
- `PYTHON_VERSION` = `3.12.10`
- `KKJ_COUNT_PER_QUERY` = `120`
- `KKJ_LOOKBACK_DAYS` = `180`
- `DIRECT_HTTP_TIMEOUT` = `15`
- `DIRECT_HOST_INTERVAL` = `2`

Build Command:

`pip install -r requirements.txt`

Start Command:

`uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Health Check Path:

`/health`

### 4. Web Serviceを再デプロイ

**Events → Manual Deploy → Clear build cache & deploy**

`/health` が `storage: postgresql` になればDB接続成功です。

### 5. Render Cron Jobを1つ作成

Dashboard → **New → Cron Job** → 同じGitHubリポジトリを選び、Root DirectoryもWeb Serviceと同じにします。

- Name: `municipal-promo-national-crawl`
- Region: Singapore
- Build Command: `pip install -r requirements.txt`
- Command: `python -m app.jobs.run_cycle`
- Schedule: `0 */6 * * *`（UTCで6時間ごと）

Cron JobのEnvironmentにもWeb Serviceと同じ `DATABASE_URL` を設定し、以下を追加します。

- `DISCOVERY_BATCH_SIZE=60`
- `DIRECT_CRAWL_BATCH_SIZE=30`
- `DIRECT_DETAIL_LIMIT=30`
- `SOURCE_DISCOVERY_LIMIT=12`
- `MUNICIPALITY_SEED_MIN=1700`

作成後、Cron Job画面の **Trigger Run** を1回押します。初回は全国自治体マスターの投入を行うため通常回より時間がかかります。

### 6. カバレッジ確認

`https://municipal-promo-search.onrender.com/api/admin/municipality-coverage`

- `municipalities`: 管理対象自治体数
- `municipalitiesWithSources`: 公示ソース発見済み自治体数
- `sources`: 直接巡回対象ページ数
- `projects`: DB内の統合案件数

Cronを繰り返すたびに `municipalitiesWithSources` と `sources` が増える設計です。全自治体サイトの構造は統一されていないため、初日100%ではなく継続的に直接収集カバレッジを上げます。

## 独立ジョブ

必要に応じて個別にも実行できます。

- `python -m app.jobs.seed_db` — 全国自治体マスター＋既知ソース投入
- `python -m app.jobs.discover_sources` — 公式トップ/sitemapから公示ページ探索
- `python -m app.jobs.crawl_due_sources` — 期限到来ソースの直接クロール
- `python -m app.jobs.refresh_kkj` — 官公需APIのみ更新
- `python -m app.migrate` — 既存`data/projects.json`をDBへ移行

## 直接収集の安全設計

- Webリクエスト中に自治体サイトへアクセスしない
- robots.txtを確認
- 同一ホスト間隔デフォルト2秒
- ETag / Last-Modifiedで条件付きGET
- 403/429/失敗ソースはバックオフ
- 1ソース失敗でバッチ全体を止めない
- 同一案件は自治体公式ソースを主値として優先
- PDF/WordはURL保持を基本とし、v6初版ではHTML中心に抽出
