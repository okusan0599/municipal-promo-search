# 自治体プロモーション公示検索（全国・段階巡回版）

都道府県、市、区、町、村を対象に、公式サイト上のプロモーション／クリエイティブ関連公示を段階的に巡回します。

## 全国化の仕組み

- J-LIS「全国自治体マップ検索」から自治体公式サイト一覧を生成
- 都道府県・市・指定都市の区・町・村を収集対象に登録
- 1回の実行で既定35自治体を巡回し、次回は続きから再開
- 既存案件と新規案件をURLで重複統合
- 締切超過を自動的に終了へ変更
- 北海道・福岡・佐賀・山口・鹿児島・兵庫の公募ページは毎回優先巡回

全国全団体を一度に巡回するとアクセス負荷と実行時間が大きいため、分割巡回にしています。`/api/status` の `municipalities_total`、`batch_start`、`next_index` で進捗を確認できます。

## Render設定

- Root Directory: `municipal-promo-app 2`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `PYTHON_VERSION=3.12.10`
- `AUTO_REFRESH=true`
- `CRAWL_BATCH_SIZE=35`

## 確実な自動更新

Render無料版の起動時更新だけでは永続性が弱いため、GitHub Actionsによる6時間ごとの分割巡回を推奨します。

`github-workflow-template/nationwide-crawl.yml` を、GitHubリポジトリ直下の `.github/workflows/nationwide-crawl.yml` として配置してください。アプリフォルダの中ではなく、リポジトリ直下です。

GitHubの `Settings → Actions → General → Workflow permissions` で `Read and write permissions` を選択すると、Actionsが更新データをコミットできます。

## API

- `/api/projects` 案件一覧
- `/api/status` 案件数・巡回進捗・取得エラー
- `/api/municipalities` 自治体ディレクトリ
- `/api/directory-status` 自治体一覧の更新状況
- `/health` 稼働確認

## 注意

全国自治体サイトは構造が統一されていないため、汎用クローラーだけで完全網羅はできません。取得漏れが多い自治体は、公式の公募・入札一覧URLを `sources.json` に優先ソースとして追加すると精度が上がります。応募前は必ず原文ページを確認してください。
