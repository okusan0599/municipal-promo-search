# 自治体プロモーション公示検索 v5 Dentsu Fit

中小企業庁「官公需情報ポータルサイト」検索APIを使い、全国47都道府県の公示候補から、電通が関与しやすいコンサル・広報PR・広告・コミュニケーション・イベント・観光・デジタル・AI/DX等の案件を優先して探すFastAPIアプリです。

## v5の主な機能

- 全国47都道府県を対象に官公需情報ポータルを横断検索
- 「電通関連度」を0〜100で自動スコアリング
- 関連度は `高 / 中 / 低` の3段階
- 検索画面は **「中以上」** をデフォルト表示
- 「すべての案件」に切り替えれば低関連案件も閲覧可能
- 11の電通関連領域を複数選択で絞り込み
- 地域ブロック → 都道府県 → 市区町村・発注機関で絞り込み
- 予算、公示日、提案・提出期限、キーワード、募集状態でも検索
- 各案件から原公示URLへ遷移
- v4のRender Free向け安定化を維持（起動時同期なし、1回1リクエスト）

## 電通関連領域

1. コンサル・戦略策定
2. 広報・PR・コミュニケーション
3. 広告・クリエイティブ
4. SNS・デジタルマーケティング
5. メディア・コンテンツ・動画
6. イベント・体験設計
7. 観光・地域ブランディング・地域創生
8. 調査・マーケティング
9. Web・アプリ・デジタルサービス
10. AI・データ活用・DX
11. ブランディング・VI/CI

関連度は案件名と公告概要のキーワードから決定論的に判定します。工事、清掃、警備、給食、物品購入等の語は減点し、戦略策定、プロモーション、コミュニケーション、AI等は加点します。最終的な応募可否や担当領域の判断は原公示を確認してください。

## 検索対象の拡張

v5では従来の広報・広告・観光・SNS・動画・Web・イベント等に加えて、以下を官公需API検索語へ追加しています。

- コンサルティング、戦略策定、基本構想、事業戦略
- マーケティング、市場調査、アンケート、調査分析
- AI、生成AI、人工知能、データ分析、データ活用、DX、デジタル活用
- コミュニケーション、広報戦略、PR、パブリシティ

## 安定性

Render Freeで503や再起動が起きにくいよう、以下を維持しています。

- Webサーバー起動時に外部APIへアクセスしない
- 1回の同期はKKJ APIへの1リクエストだけ
- 取得上限は初期値120件、最大250件
- `/health` はGET/HEADとも軽量に200応答
- キャッシュが空または古い場合だけ `/api/projects` から同期
- upstream障害時は既存キャッシュを保持
- 旧v4キャッシュに電通関連度フィールドがない場合、外部APIへ再接続せずローカルで分類情報を補完

## Render設定

Root Directoryは現在のGitHub配置に合わせてください（例: `municipal-promo-app 2`）。

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

推奨Environment Variables:

```text
PYTHON_VERSION=3.12.10
KKJ_COUNT_PER_QUERY=120
KKJ_LOOKBACK_DAYS=180
KKJ_CACHE_MINUTES=30
KKJ_TIMEOUT=25
REFRESH_TOKEN=<任意の長いランダム文字列>
```

`AUTO_REFRESH` は不要です。残っている場合は `false` で構いません。

Renderの Settings > Health Checks を使う場合:

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

`.github/workflows/keep-fresh.yml` は6時間ごとにアプリを起こし、1回の軽量同期を行います。Repository secretsには以下を設定します。

- `RENDER_APP_URL` = `https://municipal-promo-search.onrender.com`
- `REFRESH_TOKEN` = Renderと同じ値

## v6で予定する拡張

官公需情報ポータルは発注機関の全公告を保証するものではありません。次段階では、都道府県・政令指定都市・東京23区・県庁所在地・中核市などの自治体公式「公募・プロポーザル」ページを直接収集する第二経路を追加し、官公需APIに掲載されない案件を補完します。

## v5.1 分類精度修正

- 案件タイトルを最重要視し、自治体サイトのナビゲーション・JavaScript・フッター由来の語を分類から除外します。
- 説明文だけでテーマを付ける場合は、「観光誘客」「サイト制作」など業務内容を示す具体語を必須にしました。
- 「調査・分析」一般をマーケティング案件として扱わず、市場・消費者・ブランド・広報効果等の文脈に限定します。
- 物流・輸送・倉庫等は、コミュニケーション領域の明示がない場合に関連度を下げます。
- 旧キャッシュは `classificationVersion` を見て自動再分類するため、誤った旧タグを引き継ぎません。
