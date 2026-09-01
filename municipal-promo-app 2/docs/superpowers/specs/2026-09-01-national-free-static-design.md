# 全国自治体公式公示検索 v6 Free 設計

## 目的

月額課金を前提にせず、全国の都道府県・市区町村の公式サイトと官公需情報ポータルから、電通関連領域の公示候補を継続収集し、既存の検索UIで公開する。

## 採用アーキテクチャ

- 収集: GitHub Actions のスケジュール実行 / 手動実行
- 永続化: GitHub リポジトリ内の JSON ファイル
- 公開: 静的 HTML + JSON。Render Static Site を推奨し、既存 Render Free Web Service でも `python -m http.server` で互換運用可能
- 全国マスター: code4fukui/localgovjp の自治体コード・公式URLデータを初回/不足時に取得
- 公示探索: 自治体トップページと sitemap から入札・契約・公募・プロポーザル・企画提案・委託ページ候補を発見
- 案件取得: 発見済み公式ページから案件リンクを抽出し、詳細ページから案件情報を構造化
- 横断補完: 官公需情報ポータル検索APIを併用
- 統合: 自治体・タイトル・締切を基準に重複排除し、自治体公式直接取得を優先
- 分類: v5.1 の電通フィット分類を継承

## データファイル

- `data/projects.json`: UIが読む統合案件
- `data/municipalities.json`: 全国自治体マスターと探索状態
- `data/sources.json`: 発見済み公式公示ページと巡回状態
- `data/status.json`: 最新収集結果・カバレッジ・エラー件数
- `data/kkj_projects.json`: 官公需APIの最新候補キャッシュ
- `data/kkj_status.json`: 官公需API取得状態
- `data/source_seed.json`: 手動登録済み公式ソース。唐津市入札情報を初期登録

## 無料運用上の制約

GitHub Actions の無料利用枠を意識し、1回の実行で全国すべてを取得しない。自治体探索・公示ページ巡回は少量バッチに分け、各JSONに保存した `lastVerifiedAt` / `nextCrawlAt` から次回の対象を決める。1自治体・1ソースの失敗は他の処理を止めない。

## 標準バッチ設定

- 6時間ごと
- 自治体探索: 25自治体/回
- 直接ソース巡回: 12ページ/回
- 各ソースの案件詳細取得: 最大8件/回
- HTTP timeout: 12秒
- 同一ホスト間隔: 0.4秒
- 官公需API: 120件/回

## UI

`index.html` は API へ依存せず `data/status.json` と `data/projects.json` を相対URLで取得する。キャッシュ回避用にタイムスタンプクエリを付与する。検索・地域・市区町村・電通関連度・電通領域・テーマ・予算・日付の既存フィルタを維持する。

## 公開方法

### 推奨
Render Static Site。Publish Directory はプロジェクトルート。バックエンドなしで常時配信する。

### 互換
既存の Render Free Web Service を維持する場合、Start Command を `python -m http.server $PORT --bind 0.0.0.0` に変更し、同じURLを維持できる。スリープ時の初回待ちは残る。

## GitHub Actions

`.github/workflows/collect.yml` が定期実行と手動実行に対応し、収集後に `data/*.json` に差分があれば bot commit する。`permissions: contents: write` を明示する。並列実行は concurrency で抑止する。

## 成功条件

1. DB / Cron の有料サービスなしで更新できる。
2. 初回収集で全国自治体マスターが投入される。
3. 唐津市の公式入札ページが直接ソースとして存在する。
4. Actions実行ごとに探索・巡回範囲が前進する。
5. UIが `data/projects.json` の案件をフィルタ検索できる。
6. 官公需APIと自治体直接案件を重複統合できる。
7. 個別自治体サイトの取得失敗で全体処理が失敗しない。
