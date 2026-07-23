# 自治体プロモーション公示検索 LIVE版

既存UIを保ったまま、自治体公式ページを巡回して案件をSQLiteへ蓄積し、APIまたは静的JSONから表示する構成です。

## できること

- 自治体公式ページの定期巡回
- プロモーション／広報／広告／観光／SNS／動画／Web／イベント等の案件候補抽出
- 公示日・提出期限・予算・テーマ・原文URLの構造化
- 締切日を使った「募集中／締切間近／募集終了」の自動判定
- SQLiteへの履歴保存
- FastAPIの検索API
- GitHub Actionsによる毎日06:15（日本時間）の自動更新
- APIがない静的ホスティングでは `data/projects.json` を利用

## ローカル起動

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.crawler
uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000` を開きます。

## データ更新

```bash
python -m app.crawler
```

対象自治体は `sources.json` に追加します。巡回先は自治体公式の一覧ページを指定してください。

## API

`GET /api/projects`

利用可能なパラメータ：`area`, `region`, `budget_min`, `budget_max`, `status`, `q`

## 公開方法

### GitHub Pages

リポジトリへ配置し、GitHub Actionsを有効にすると `data/projects.json` が日次更新されます。静的ページとして公開できます。

### Render / Railway / Cloud Run

起動コマンドを以下にします。

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

この場合はSQLite/API経由で表示されます。

## 重要な運用上の注意

- 自治体ごとにHTML構造が異なるため、初期の汎用抽出で拾えないサイトは個別アダプターを追加します。
- PDF内だけにある予算・プレゼン日は、追加のPDF解析ルールまたは確認画面で補完する想定です。
- robots.txt、利用規約、アクセス頻度を確認し、低頻度巡回を守ってください。
- 抽出結果には誤りがあり得るため、応募前には必ず「自治体ページを見る」から原文を確認してください。
