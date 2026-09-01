# 自治体プロモーション公示検索 v6 Free

全国の都道府県・市区町村の公式サイトを分割巡回し、官公需情報ポータル検索APIも併用して、電通が携われる可能性のある公示を検索する無料運用版です。

## 無料版の構成

- 収集: GitHub Actions
- 保存: リポジトリ内の `data/*.json`
- 検索画面: `index.html`
- 公式サイト直接収集: 入札・契約・公募・プロポーザル・企画提案・業務委託ページを探索
- 横断補完: 官公需情報ポータル検索API
- 初期直接ソース: 唐津市 入札情報 `https://www.city.karatsu.lg.jp/site/nyusatsu/`

月額のデータベースサービスや定期ジョブサービスを必須にしません。GitHub Actions の利用枠内で分割巡回します。

## 1. GitHub に上書き

### 1-A. アプリ本体

現在の `municipal-promo-search` リポジトリで、Render が参照しているフォルダ（これまでの環境では `municipal-promo-app 2`）を開きます。

`Add file` → `Upload files` から、このZIPを展開した**中身のうち `.github` 以外**を上書きして `Commit changes` します。

重要なファイル:

- `index.html`
- `app/`
- `data/`
- `requirements.txt`

### 1-B. GitHub Actions の workflow はリポジトリ直下へ

GitHub Actions が認識する workflow は、必ずリポジトリ直下の `.github/workflows/` に置く必要があります。`municipal-promo-app 2/.github/` では動きません。

リポジトリのトップ画面に戻り、`Add file` → `Create new file` を選び、ファイル名欄へ次を入力します。

```text
.github/workflows/collect.yml
```

この配布物の `.github/workflows/collect.yml` の内容を貼り付けて `Commit changes` します。workflow 内の `APP_DIR` は現在の GitHub フォルダ名 `municipal-promo-app 2` に設定済みです。

## 2. GitHub Actions の書き込みを許可

GitHub のリポジトリで:

`Settings` → `Actions` → `General` → `Workflow permissions`

`Read and write permissions` を選択して保存します。

## 3. 初回収集を手動実行

GitHub の `Actions` タブを開き、`Collect municipal procurement data` を選びます。

`Run workflow` → `Run workflow` を押します。

初回実行では全国自治体マスターを投入し、官公需APIの取得と自治体公式公示ページの探索を小さいバッチで開始します。以後は6時間ごとに自動実行されます。

標準設定:

- 自治体探索 25団体/回
- 公式ソース巡回 12ページ/回
- 1ソースあたり詳細 8案件まで
- 官公需API 120件/回

全国すべてを一回で巡回せず、Actionsを回すたびにカバレッジを前進させます。

## 4A. 既存 Render URL をそのまま使う方法

現在の Render Free Web Service を残す場合、同じ公開URLを維持できます。

Render の `municipal-promo-search` → `Settings` で Start Command を次に変更します。

```text
python -m http.server $PORT --bind 0.0.0.0
```

Build Command は空欄、または次で構いません。

```text
echo static
```

Health Check Path を設定する場合は `/index.html` にします。

GitHub の `data/*.json` が更新されるたびに Render が再デプロイし、検索画面に反映されます。Free Web Service のため、長時間アクセスがない後の初回表示には待ち時間が発生する場合があります。

## 4B. Render Static Site にする方法（推奨）

スリープを避けたい場合は Render Static Site を使います。

Render → `+ New` → `Static Site` → 同じ GitHub リポジトリを選択します。

設定例:

- Root Directory: `municipal-promo-app 2`（GitHub上の実際の配置に合わせる）
- Build Command: `echo static`
- Publish Directory: `.`

作成後に発行される `onrender.com` URLが新しい検索URLです。

## 5. データ確認

検索画面は同一サイトの次のJSONを読みます。

- `data/projects.json` — 統合案件
- `data/status.json` — 収集状況
- `data/municipalities.json` — 全国自治体マスター
- `data/sources.json` — 発見済み自治体公式公示ページ

`data/status.json` の `coverage` で、自治体総数・公示ページ発見済み自治体数・直接ソース数・案件数を確認できます。

## 6. 自動更新が止まった場合

GitHub → `Actions` → `Collect municipal procurement data` の最新実行を開きます。

個別自治体のタイムアウトやアクセス拒否は `data/status.json` に記録し、他自治体の収集は継続します。

## データの優先順位

同一案件が複数経路から見つかった場合、自治体公式ページから直接取得した情報を優先し、官公需APIを補完ソースとして保持します。

応募判断前には、検索結果の「原公示を見る」から自治体公式の公告を確認してください。
