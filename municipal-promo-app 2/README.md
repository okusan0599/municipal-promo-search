# 自治体プロモーション公示検索 v3

中小企業庁「官公需情報ポータルサイト検索API」を主データ源にしたライブ検索版です。

## 何が変わったか

- 自治体トップページを順番に巡回する方式を主系統から外し、官公需情報ポータルの公式APIから全国横断で同期します。
- API結果の `ExternalDocumentURI` を原公示リンクとして使用します。
- 公告本文 (`ProjectDescription`) から提案期限・プレゼン日・予算を可能な範囲で抽出します。
- 地域ブロック、47都道府県、市区町村・発注機関、テーマ、予算、公示日、期限で絞り込めます。
- APIキャッシュは既定30分。Render再起動時にも初回同期をバックグラウンドで行います。

## Render

Root Directory: 現在このファイル群を置いているフォルダ（例 `municipal-promo-app 2`）

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment:

```text
PYTHON_VERSION=3.12.10
AUTO_REFRESH=true
KKJ_CACHE_MINUTES=30
KKJ_LOOKBACK_DAYS=180
KKJ_COUNT_PER_QUERY=500
KKJ_TIMEOUT=25
```

`REFRESH_TOKEN` は任意です。設定した場合、`POST /api/refresh` は `X-Refresh-Token` ヘッダーが必要です。

## URL

- 検索画面 `/`
- 案件JSON `/api/projects`
- 同期状態 `/api/status`
- ヘルスチェック `/health`

## データ出典

本アプリは中小企業庁「官公需情報ポータルサイト検索API」を利用します。官公需情報ポータルの規約に従い、画面内に同APIの利用とポータルへのリンクを明記しています。

官公需情報ポータル自体も全ての発注情報の提供を保証していません。応募判断前に必ず原公示を確認してください。
