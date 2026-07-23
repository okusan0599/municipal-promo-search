# 自治体プロモーション公示検索（6地域ライブ収集版）

対象地域：北海道、福岡県、佐賀県、山口県、鹿児島県、兵庫県。

## Render設定

- Root Directory: GitHub上の実際のフォルダ名（現在の構成なら `municipal-promo-app 2`）
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment variable: `PYTHON_VERSION=3.12.10`
- Environment variable: `AUTO_REFRESH=true`

起動時、データが未取得または12時間以上古い場合、6地域の公式ページをバックグラウンド巡回します。初回は数分かかることがあります。

## 手動更新（任意）

RenderのEnvironmentに `REFRESH_TOKEN` を設定すると、次のPOSTで更新を開始できます。

```bash
curl -X POST https://YOUR-SERVICE.onrender.com/api/refresh \
  -H "X-Refresh-Token: YOUR_TOKEN"
```

## API

- `/api/projects` 案件一覧
- `/api/status` 最終更新日時、件数、取得エラー
- `/health` 稼働確認

## 注意

自治体サイトは形式が統一されていないため、抽出漏れや日付・予算の未確認が発生します。応募前に必ず「自治体ページを見る」から原文を確認してください。
