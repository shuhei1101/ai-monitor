# ai-monitor 規約: 外部API

利用する外部 API 1 つにつき 1 ページの Wiki を作成し、**そのプロジェクトで実際に使うエンドポイントだけ** を公式ドキュメントから抽出して整理する。

公式ドキュメントは情報量が多く読みづらいため、ここを見るだけで実装に必要な情報（認証セットアップ + 使うエンドポイントのリクエスト/レスポンス）が揃う状態を目指す。

配置先は `docs/wiki/外部API/{API名}.md`（例: `docs/wiki/外部API/OpenAI.md`）。
新規作成時は `docs/wiki/外部API/README.md`（一覧）に行を追加してリンクを張る。

各セクションの書き方を「記述例 + 補足」で定義する。

## セクション一覧

| セクション | サブセクション | 必須or条件 | 担当 | 補足 |
| --- | --- | --- | --- | --- |
| `## 概要` | - | 必須 | issue-arch / issue-ui | - |
| `## 現在のバージョン情報` | - | 必須 | issue-arch / issue-ui | - |
| `## 認証セットアップ` | - | 必須 | issue-arch / issue-ui | - |
| `## レートリミット・課金` | - | 必須 | issue-arch / issue-ui | - |
| `## エンドポイント一覧` | - | 必須 | issue-arch / issue-ui | 全エンドポイントの索引 |
| `## {METHOD} {パス}` | `### リクエスト` / `### レスポンス` / `### ステータスコード` | 必須（一覧表の各行につき 1 セクション） | issue-arch / issue-ui | - |

## `## 概要`

### 記述例

```markdown
## 概要

OpenAI が提供する LLM / 埋め込み / 音声 API。
```

### 補足

- API が何をするものかを 1〜3 行で要約する
- 自プロジェクトでの用途・採用箇所は書かない

## `## 現在のバージョン情報`

### 記述例

```markdown
## 現在のバージョン情報

| 項目 | 内容 |
| --- | --- |
| API バージョン | `2024-10-21`（または `v1`） |
| ベース URL | `https://api.openai.com/v1` |
| 公式 URL | https://openai.com/api/ |
| 公式ドキュメント | https://platform.openai.com/docs/api-reference |
```

### 補足

- API バージョンは header 指定型（`OpenAI-Beta` など）か URL 埋め込み型（`/v1/...`）かを書く
- ベース URL を明示することで、各エンドポイントサブセクションは相対パスだけで書ける
- 公式 URL は API のトップページ、公式ドキュメントは API リファレンスの URL
- 採用時点のバージョンを固定で記録し、アップグレード時にこことエンドポイント記述を見直す

## `## 認証セットアップ`

### 記述例

````markdown
## 認証セットアップ

認証方式: Bearer トークン（API キー）

### 取得手順

1. https://platform.openai.com/api-keys にアクセス
2. `Create new secret key` で API キーを生成
3. 生成されたキー（`sk-...`）を控える（再表示不可）

### env 変数

```bash
# .env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### リクエスト時の利用

```ts
fetch("https://api.openai.com/v1/chat/completions", {
  headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
  ...
});
```
````

### 補足

- 認証方式（Bearer / API Key Header / OAuth2 / JWT など）を最上部に明記
- キー取得の **公式ページ URL + 具体手順** を書く（公式 UI が変わる前提で番号付き手順）
- env 変数名は `.env.example` と一致させる
- **API キーをリポジトリにコミットしない** ことを補足列でも警告
- OAuth など複雑な認可フローの場合は別途シーケンス図を貼る

## `## レートリミット・課金`

### 記述例

```markdown
## レートリミット・課金

### レートリミット

| モデル | RPM | TPM | 補足 |
| --- | --- | --- | --- |
| `gpt-4o-mini` | 500 | 200,000 | tier 1 |
| `text-embedding-3-small` | 3,000 | 1,000,000 | tier 1 |

超過時は HTTP 429 を返す。リトライは Exponential Backoff（1s → 2s → 4s）で最大 3 回。

### 課金単価

公式: https://openai.com/api/pricing/

| モデル | 入力（1M tokens） | キャッシュ入力（1M tokens） ※1 | 出力（1M tokens） | 補足 |
| --- | --- | --- | --- | --- |
| `gpt-4o-mini` | $0.150 | $0.015 | $0.600 | - |
| `text-embedding-3-small` | $0.020 | - | - | - |

※1: OpenAI のプロンプトキャッシュヒット時のトークン単価（入力料金の 1/10）。
　同一プロンプト先頭が再利用された場合に自動適用される。
　詳細: https://platform.openai.com/docs/guides/prompt-caching
```

### 補足

- レートリミットの単位（RPM = Requests Per Minute、TPM = Tokens Per Minute など）を必ず明記
- 超過時の HTTP ステータスコードと、リトライ戦略（Exponential Backoff / Circuit Breaker）を書く
- **課金単価は公式の Pricing ページ URL を必ず併記**（変動があるため出典を明示）
- API 固有の特殊な課金体系（プロンプトキャッシュ・バッチ割引・無料枠など）は表に列を追加し、表外に `※n` で補足
- 採用時点で固定値を記録、変動時はここを更新

## `## エンドポイント一覧`

このプロジェクトで使うエンドポイントの索引。

### 記述例

```markdown
## エンドポイント一覧

API バージョン: `v1`

| METHOD | パス | 用途 | 補足 |
| --- | --- | --- | --- |
| POST | [`/chat/completions`](#post-chatcompletions) | チャット形式の LLM 応答生成 | - |
| POST | [`/embeddings`](#post-embeddings) | テキストのベクトル埋め込み生成 | - |
```

### 補足

**パス列:**
- ベース URL からの相対パスを、詳細セクションへのリンクで書く（アンカー = 見出しを小文字化 + 空白を `-` に置換 + 記号除去）

**用途列:**
- 1 行で要約。
  詳細は `## {METHOD} {パス}` セクション側で書く

**補足:**
- 表の上に **採用している API バージョン** を必ず明記
- 表とセクションの順序を揃える（使用頻度の高い順）
- 新規エンドポイント追加時は **必ずこの索引にも 1 行追加**（手動更新）

## `## {METHOD} {パス}`

エンドポイントごとの詳細。
一覧表の各行につき 1 つの H2 を作成する。

### 記述例

````markdown
## POST `/chat/completions`

チャット履歴を渡して LLM 応答を生成する。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `model` | `string` | ✅ | - | モデル名 | - | - |
| `messages` | `{ role, content }[]` | ✅ | - | チャット履歴 | - | 子フィールドは下の行で展開 |
| `messages[].role` | `"system" or "user" or "assistant"` | ✅ | - | メッセージ送信者の役割 | - | `system`=システム指示 / `user`=ユーザー入力 / `assistant`=モデルの過去応答 |
| `messages[].content` | `string` | ✅ | - | メッセージ本文 | - | - |
| `temperature` | `number` | - | `1` | 創造性度合い | 0〜2 | 0 で決定的・2 で発散 |
| `max_tokens` | `number` | - | `inf` | 生成する最大トークン数 | - | - |
| `stream` | `boolean` | - | `false` | true で SSE ストリーミング | - | - |
| `response_format.type` | `"text" or "json_object"` | - | `"text"` | 出力フォーマット種別 | - | `json_object`=有効 JSON 強制 |

リクエスト例:

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    { "role": "system", "content": "あなたは有能なアシスタントです" },
    { "role": "user", "content": "Hello" }
  ],
  "temperature": 0.7,
  "max_tokens": 512
}
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `id` | `string` | 応答 ID | - | - |
| `model` | `string` | 実際に使われたモデル | - | - |
| `choices[].message.content` | `string` | 生成されたテキスト | - | - |
| `choices[].finish_reason` | `"stop" or "length" or "tool_calls" or "content_filter"` | 終了理由 | - | `stop`=自然終了 / `length`=`max_tokens` 到達 / `tool_calls`=関数呼び出し発生 / `content_filter`=フィルタ遮断 |
| `usage.prompt_tokens` | `number` | 入力トークン数 | - | - |
| `usage.completion_tokens` | `number` | 出力トークン数 | - | - |

レスポンス例:

```json
{
  "id": "chatcmpl-abc123",
  "model": "gpt-4o-mini-2024-07-18",
  "choices": [
    { "message": { "role": "assistant", "content": "こんにちは" }, "finish_reason": "stop" }
  ],
  "usage": { "prompt_tokens": 12, "completion_tokens": 34 }
}
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `401` | API キー不正 | - |
| `429` | レートリミット超過 | Exponential Backoff で最大 3 回リトライ |
| `500` / `503` | サーバー側の一時的障害 | Exponential Backoff で最大 3 回リトライ |
````

### 補足

**`### リクエスト`:**
- カラム: `パラメータ / 型 / 必須 / デフォルト / 説明 / 制限 / 補足`（7 列。必須は ✅ / `-`）
- query パラメータ・パスパラメータもこの表に書く
- 表の直後に `リクエスト例:` を JSON コードブロックで書く（body を持たない GET / DELETE はリクエストラインをテキストで書く）

**`### レスポンス`:**
- カラム: `フィールド / 型 / 説明 / 制限 / 補足`（5 列）
- 表の直後に `レスポンス例:` を JSON コードブロックで書く
- 別エンドポイントと同形のレスポンスは「`{METHOD} {パス}` のレスポンスと同形」と書いて表を省略してよい

**`### ステータスコード`:**
- カラム: `ステータスコード / 発生条件 / 補足`（3 列）。
  正常・異常とも網羅する
- リトライ戦略（Exponential Backoff 等）は補足列に書く

**パラメータ / レスポンスフィールドの網羅性:**
- 「現在使っているもの」だけでなく **主要なパラメータ / フィールドも全部** 載せる
- 理由: 採用後にチューニングで別パラメータを足す可能性が高く、その都度公式ドキュメントを引き直すのを避けたい
- 公式ドキュメント全列挙ではなく **主要 = 通常使われる範囲** に絞る（明らかに使わない beta / deprecated は除外）

**「デフォルト」列の書き方:**
- 任意パラメータの省略時デフォルト値を書く（例: `1` / `false` / `null` / `"text"`）
- 必須パラメータは `-` 固定
- レスポンスフィールド表には不要（サーバが必ず値を返すため）

**enum パラメータ / フィールド（値で動作が変わるもの）の書き方:**
- 行は増やさない（1 パラメータ 1 行）
- 型列: `"a" or "b" or "c"` で取りうる値を列挙
- 補足列: 各値の意味を `a=～ / b=～ / c=～` 形式で書く
- 値が多い（5 個以上など）ときのみ別表 / 別セクションに切り出してよい

**入れ子（オブジェクト / 配列の中身）の書き方:**
- 親パラメータがオブジェクトや配列の場合、子フィールドは **行を追加** して個別に書く
- パラメータ列の表記:
  - オブジェクトの子: `parent.child`
  - 配列要素の子: `parent[].child`
  - 多段ネスト: `parent[].grandchild.field` のように `.` / `[].` を繋げる
- 親行の補足列に「子フィールドは下の行で展開」と書く
- 深すぎる構造（3 段以上 / 子が 10 個以上）は別セクションに切り出してよい
