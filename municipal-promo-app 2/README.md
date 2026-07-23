# 自治体プロモーション案件検索 第一段階・最大構成

## 対象
- 47都道府県
- 20政令指定都市
- 東京23区
- 合計 90 公式サイト

J-LISへ実行時アクセスせず、`sources.json` の固定公式URLを使います。各公式トップページから、入札・契約・調達・公募・プロポーザル等のハブページを探索し、クリエイティブ関連案件を抽出します。

## Render環境変数
- `PYTHON_VERSION=3.12.10`
- `AUTO_REFRESH=true`
- `CRAWL_BATCH_SIZE=20`（無料版推奨。増やす場合は30程度まで）
- `REFRESH_INTERVAL_HOURS=6`
- `REFRESH_TOKEN=` 任意の長いランダム文字列

## Render設定
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## 確認URL
- `/api/status` 巡回状況
- `/api/projects` 案件JSON
- `/api/sources` 対象公式サイト一覧

## GitHub Actions（推奨）
`.github/workflows/crawl.yml` を同梱。リポジトリ Settings > Secrets and variables > Actions に以下を登録します。
- `RENDER_APP_URL` = `https://municipal-promo-search.onrender.com`
- `REFRESH_TOKEN` = Renderと同じ値

6時間ごとにRenderを起こし、次の20自治体を巡回します。約5回で90ソースを一巡します。

## 注意
- 自治体サイトの構造差により漏れはあります。応募判断は必ず原文で確認してください。
- Render無料版のローカルJSONは再デプロイで消える場合があります。本番運用ではPostgreSQLへ移行してください。
- 公式サイトへの負荷を避けるため低頻度・逐次アクセスです。
