# 自治体プロモーション公示検索 v6.3 Free

全国の都道府県・市区町村の公式サイトを分割巡回し、官公需情報ポータル検索APIも併用して、電通が携われる可能性のある公示を検索する無料運用版です。


## v6.3 へのアップグレード手順（既存サイト用）

1. `municipal-promo-national-free-v6.3-upgrade.zip` を展開し、GitHub の `municipal-promo-app 2` に中身を上書きします。このアップグレードZIPには `data/` を含めないため、現在の収集済み案件は消えません。
2. リポジトリ直下の `.github/workflows/collect.yml` は、別添の `collect-v6.3.yml` の内容で置き換えます。
3. GitHub Actions の `Collect municipal procurement data` を一度 `Run workflow` します。以降は1時間ごとに、現行案件と過去実績を分割収集します。
4. Render Static Site は GitHub の更新を自動デプロイします。公開URLは既存の `municipal-promo-search-1.onrender.com` をそのまま利用できます。

## 無料版の構成

- 収集: GitHub Actions
- 保存: リポジトリ内の `data/*.json`
- 過去実績: 自治体公式の落札結果・契約結果・選定結果・結果PDFを分割収集し、現行案件と過去3年度を照合
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
- `requirements.txt`
- `VERSION`

既存の `data/` はそのまま残します。アップグレードZIPから上書きしません。

### 1-B. GitHub Actions の workflow はリポジトリ直下へ

GitHub Actions が認識する workflow は、必ずリポジトリ直下の `.github/workflows/` に置く必要があります。`municipal-promo-app 2/.github/` では動きません。

リポジトリのトップ画面に戻り、`Add file` → `Create new file` を選び、ファイル名欄へ次を入力します。

```text
.github/workflows/collect.yml
```

別添の `collect-v6.3.yml` の内容を貼り付けて `Commit changes` します。workflow 内の `APP_DIR` は現在の GitHub フォルダ名 `municipal-promo-app 2` に設定済みです。

## 2. GitHub Actions の書き込みを許可

GitHub のリポジトリで:

`Settings` → `Actions` → `General` → `Workflow permissions`

`Read and write permissions` を選択して保存します。

## 3. 初回収集を手動実行

GitHub の `Actions` タブを開き、`Collect municipal procurement data` を選びます。

`Run workflow` → `Run workflow` を押します。

初回実行では全国自治体マスターを投入し、官公需APIの取得と自治体公式公示ページの探索を小さいバッチで開始します。以後は1時間ごとに自動実行されます。

標準設定:

- 自治体探索 100団体/回
- 公式ソース巡回 50ページ/回
- 1ソースあたり詳細 8案件まで
- 官公需API 120件/回
- 過去実績ソース巡回 30ページ/回
- 過去実績PDFは1ファイル20ページまで解析

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
- `data/history_sources.json` — 落札結果・契約結果・選定結果などの公式ページ
- `data/history_awards.json` — 過去の受託・落札業者実績

`data/status.json` の `coverage` で、自治体総数・公示ページ発見済み自治体数・直接ソース数・案件数を確認できます。

## 6. 自動更新が止まった場合

GitHub → `Actions` → `Collect municipal procurement data` の最新実行を開きます。

個別自治体のタイムアウトやアクセス拒否は `data/status.json` に記録し、他自治体の収集は継続します。

## データの優先順位

同一案件が複数経路から見つかった場合、自治体公式ページから直接取得した情報を優先し、官公需APIを補完ソースとして保持します。

応募判断前には、検索結果の「原公示を見る」から自治体公式の公告を確認してください。


## v6.1 終了案件フィルタ改善

- タイトルに「終了いたしました」「募集終了」「受付終了」「公募終了」等がある案件を終了扱いにします。
- 選定結果・契約結果ページも終了扱いにします。
- 既存JSONに残る旧案件もGitHub Actions実行時に再判定します。
- 静的UI側でも終了表記を再判定するため、古いJSONでも通常検索から除外されます。
- 自治体ページの本文抽出は案件タイトルより前のサイト共通ナビゲーションを除外します。


## v6.2 提出期限ポリシー

通常の検索画面には提案・提出期限を取得できた案件だけを表示します。内部JSONには期限未取得案件も保持し、次回巡回で再取得します。


## v6.3 過去3年の受託業者実績

各現行案件について、同じ自治体の公式な落札結果・契約結果・プロポーザル選定結果を収集し、直近3年度の類似案件を照合します。

検索カードの「過去3年の類似実績」には、次を表示します。

- 年度
- 類似案件名
- 受託・落札業者
- 契約・落札金額（公開されている場合）
- 類似度
- 公式結果ページへのリンク
- 受託回数の集計

案件区分は次の4つです。

- `継続・類似実績あり` — 過去3年度に類似案件の公式結果を確認
- `新規（明記）` — 現行公示が新規事業等と明記
- `新規推定` — 過去3年度の結果公開範囲を確認したが類似案件なし
- `未確認` — 過去結果ページの収集・照合がまだ不十分

「見つからない＝新規」とは断定せず、公開範囲を3年度確認できない場合は `未確認` とします。
