# gh-kit 規約: 外部API

利用する外部 API 1 つにつき 1 ページの Wiki を作成し、**そのプロジェクトで実際に使うエンドポイントだけ** を公式ドキュメントから抽出して整理する。

公式ドキュメントは情報量が多く読みづらいため、ここを見るだけで実装に必要な情報（認証セットアップ + 使うエンドポイントのリクエスト/レスポンス）が揃う状態を目指す。

配置先は `docs/wiki/外部API/{API名}.md`（例: `docs/wiki/外部API/OpenAI.md`）。
新規作成時は `docs/wiki/外部API/README.md`（一覧）に行を追加してリンクを張る。

各セクションの書き方を「記述例 + 補足」で定義する。

## 担当セクション一覧

| No | セクション | サブセクション | 必須or条件 | 担当 | 補足 |
| --- | --- | --- | --- | --- | --- |
| 1 | `## 概要` | - | 必須 | issue-arch / issue-ui | - |
| 2 | `## 現在のバージョン情報` | - | 必須 | 〃 | - |
| 3 | `## 認証セットアップ` | - | 必須 | 〃 | - |
| 4 | `## レートリミット・課金` | - | 必須 | 〃 | - |
| 5 | `## エンドポイント一覧` | `### {METHOD} {パス}` | 必須（一覧表の各行につき 1 サブセクション） | 〃 | - |

## `## 概要`

### 記述例

```markdown
## 概要

OpenAI が提供する LLM / 埋め込み / 音声 API。

このプロジェクトでは Chat Completions（GPT-4o-mini）と Embeddings（text-embedding-3-small）を使用する。
```

### 補足

- API が何をするものかを 1〜3 行で要約（自プロジェクトでの使い道に絞った言葉で）
- 使用するモデル / プランがあれば併記

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

| No | モデル | RPM | TPM | 補足 |
| --- | --- | --- | --- | --- |
| 1 | `gpt-4o-mini` | 500 | 200,000 | tier 1 |
| 2 | `text-embedding-3-small` | 3,000 | 1,000,000 | 〃 |

超過時は HTTP 429 を返す。リトライは Exponential Backoff（1s → 2s → 4s）で最大 3 回。

### 課金単価

公式: https://openai.com/api/pricing/

| No | モデル | 入力（1M tokens） | キャッシュ入力（1M tokens） ※1 | 出力（1M tokens） | 補足 |
| --- | --- | --- | --- | --- | --- |
| 1 | `gpt-4o-mini` | $0.150 | $0.015 | $0.600 | - |
| 2 | `text-embedding-3-small` | $0.020 | - | - | - |

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

このプロジェクトで使うエンドポイントを 1 表で俯瞰し、表の下に各エンドポイントの詳細サブセクション（`### {METHOD} {パス}`）を並べる。

### 記述例

````markdown
## エンドポイント一覧

API バージョン: `v1`

| No | METHOD | パス | 用途 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | POST | `/chat/completions` | チャット形式の LLM 応答生成 | - |
| 2 | POST | `/embeddings` | テキストのベクトル埋め込み生成 | - |
| 3 | GET | `/models` | 利用可能モデル一覧の取得 | - |

### POST `/chat/completions`

チャット履歴を渡して LLM 応答を生成する。

**リクエスト body（パラメータ）**

| No | パラメータ | 型 | 必須 | 既定 | 説明 | 例 | 補足 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `model` | `string` | 必須 | - | モデル名 | `"gpt-4o-mini"` | 採用モデルは `## 現在のバージョン情報` 参照 |
| 2 | `messages` | `{ role, content }[]` | 必須 | - | チャット履歴 | `[{ role: "user", content: "Hi" }]` | 子フィールドは下の 2-1 / 2-2 参照 |
| 2-1 | `messages[].role` | `"system" or "user" or "assistant"` | 必須 | - | メッセージ送信者の役割 | `"user"` | `system`=システム指示 / `user`=ユーザー入力 / `assistant`=モデルの過去応答（履歴再投入用） |
| 2-2 | `messages[].content` | `string` | 必須 | - | メッセージ本文 | `"Hello"` | - |
| 3 | `temperature` | `number` | 任意 | `1` | 0〜2 の創造性度合い | `0.7` | 0 で決定的・2 で発散 |
| 4 | `max_tokens` | `number` | 任意 | `inf` | 生成する最大トークン数 | `512` | プロンプトキャッシュ計算外 |
| 5 | `top_p` | `number` | 任意 | `1` | nucleus sampling の閾値 | `0.9` | temperature と排他推奨 |
| 6 | `n` | `number` | 任意 | `1` | 生成する候補数 | `3` | コストは n 倍 |
| 7 | `stop` | `string or string[]` | 任意 | `null` | ストップシーケンス | `["\n\n"]` | - |
| 8 | `stream` | `boolean` | 任意 | `false` | true で SSE ストリーミング | `true` | - |
| 9 | `presence_penalty` | `number` | 任意 | `0` | -2〜2 新規話題促進 | `0.5` | - |
| 10 | `frequency_penalty` | `number` | 任意 | `0` | -2〜2 反復抑制 | `0.3` | - |
| 11 | `response_format` | `object` | 任意 | `{type:"text"}` | 応答形式指定 | `{ type: "json_object" }` | 子フィールドは下の 11-1 参照 |
| 11-1 | `response_format.type` | `"text" or "json_object"` | 任意 | `"text"` | 出力フォーマット種別 | `"json_object"` | `text`=自然文 / `json_object`=有効 JSON 強制 |
| 12 | `tools` | `Tool[]` | 任意 | `undefined` | 関数呼び出し定義 | `[{ type: "function", function: {...} }]` | function calling 用。`Tool` 構造の詳細は公式リファレンス参照 |

**リクエスト body（コード例）**

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

**レスポンス 200 OK（フィールド）**

| No | フィールド | 型 | 説明 | 例 | 補足 |
| --- | --- | --- | --- | --- | --- |
| 1 | `id` | `string` | 応答 ID | `"chatcmpl-abc123"` | - |
| 2 | `object` | `string` | 種別 | `"chat.completion"` | - |
| 3 | `created` | `number` | 生成時刻（UNIX 秒） | `1730000000` | - |
| 4 | `model` | `string` | 実際に使われたモデル | `"gpt-4o-mini-2024-07-18"` | - |
| 5 | `choices[].index` | `number` | 候補インデックス | `0` | - |
| 6 | `choices[].message.role` | `"assistant"` | `"assistant"` 固定 | `"assistant"` | - |
| 7 | `choices[].message.content` | `string` | 生成されたテキスト | `"こんにちは"` | - |
| 8 | `choices[].finish_reason` | `"stop" or "length" or "tool_calls" or "content_filter"` | 終了理由 | `"stop"` | `stop`=自然終了 / `length`=`max_tokens` 到達 / `tool_calls`=関数呼び出し発生 / `content_filter`=フィルタ遮断 |
| 9 | `usage.prompt_tokens` | `number` | 入力トークン数 | `12` | - |
| 10 | `usage.completion_tokens` | `number` | 出力トークン数 | `34` | - |
| 11 | `usage.total_tokens` | `number` | 合計 | `46` | - |
| 12 | `usage.prompt_tokens_details.cached_tokens` | `number` | キャッシュヒット入力トークン | `8` | プロンプトキャッシュ集計用 |

**レスポンス 200 OK（コード例）**

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1730000000,
  "model": "gpt-4o-mini-2024-07-18",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "こんにちは" },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 34,
    "total_tokens": 46,
    "prompt_tokens_details": { "cached_tokens": 8 }
  }
}
```

**主なエラー**

| No | ステータス | 原因 | 対処 | 補足 |
| --- | --- | --- | --- | --- |
| 1 | 401 | API キー不正 | env 変数確認 | - |
| 2 | 429 | レートリミット超過 | Exponential Backoff で最大 3 回リトライ | - |
| 3 | 500 / 503 | サーバー側の一時的障害 | 〃 | - |

**呼び出し例**

```ts
const res = await fetch("https://api.openai.com/v1/chat/completions", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
  },
  body: JSON.stringify({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: "Hello" }],
  }),
});
const data = await res.json();
```
````

### 補足

**一覧表の METHOD 列:**
- `GET` / `POST` / `PUT` / `PATCH` / `DELETE` のいずれか

**一覧表のパス列:**
- ベース URL からの相対パスで書く（現在のバージョン情報のベース URL と連結する前提）

**一覧表の用途列:**
- 1 行で要約。詳細パラメータは書かない（下の `### {METHOD} {パス}` 側で書く）

**各エンドポイントサブセクション:**
- 一覧表の各行につき 1 つ作成（`### {METHOD} {パス}`）
- 構成: 1〜2 行の説明 → **リクエスト body（パラメータ）** 表 → **リクエスト body（コード例）** → **レスポンス 200 OK（フィールド）** 表 → **レスポンス 200 OK（コード例）** → **主なエラー** 表 → **呼び出し例**
- パラメータ表カラム: `No` / `パラメータ` / `型` / `必須` / `既定` / `説明` / `例` / `補足` の 8 列固定
- レスポンスフィールド表カラム: `No` / `フィールド` / `型` / `説明` / `例` / `補足` の 6 列固定（必須/任意・既定は不要）
- エラー表カラム: `No` / `ステータス` / `原因` / `対処` / `補足` の 5 列固定（リトライ戦略も対処欄に書く）

**パラメータ / レスポンスフィールドの網羅性:**
- 「現在使っているもの」だけでなく **主要なパラメータ / フィールドも全部** 載せる
- 理由: 採用後にチューニングで別パラメータを足す可能性が高く、その都度公式ドキュメントを引き直すのを避けたい
- 公式ドキュメント全列挙ではなく **主要 = 通常使われる範囲** に絞る（明らかに使わない beta / deprecated は除外）

**「既定」列の書き方:**
- 任意パラメータの省略時デフォルト値を書く（例: `1` / `false` / `null` / `undefined` / `"text"`）
- 必須パラメータは `-` 固定
- 公式が明示してない場合は `undefined` または `-`
- レスポンスフィールド表には不要（サーバが必ず値を返すため）

**「例」列の書き方:**
- 実装でそのまま使えそうな具体値を書く（ダミー値ではなく現実的な値）
- 長い構造は `{ a: 1, ... }` で省略可

**enum パラメータ / フィールド（値で動作が変わるもの）の書き方:**
- 行は増やさない（1 パラメータ 1 行）
- 型列: `"a" or "b" or "c"` で取りうる値を列挙
- 例列: 代表値 1 つ（例: `"a"`）
- 補足列: 各値の意味を `a=～ / b=～ / c=～` 形式で書く
- 値が多い（5 個以上など）ときのみ別表 / 別サブセクションに切り出してよい

**入れ子（オブジェクト / 配列の中身）の書き方:**
- 親パラメータがオブジェクトや配列の場合、子フィールドは **行を追加** して個別に書く
- 親の No は通常の連番（`2`）、子の No は親に枝番（`2-1` / `2-2`）
- パラメータ列の表記:
  - オブジェクトの子: `parent.child`
  - 配列要素の子: `parent[].child`
  - 多段ネスト: `parent[].grandchild.field` のように `.` / `[].` を繋げる
- 親行の補足列に「子フィールドは下の N-X 参照」と書いて誘導する
- 例列: 親行は配列/オブジェクト全体の例、子行はその値だけ
- 深すぎる構造（3 段以上 / 子が 10 個以上）は別サブセクションに切り出してよい

**コード例の役割分担:**
- **リクエスト body（コード例）** = 実際に送る JSON ペイロード（fetch の `body` に渡すもの）
- **レスポンス 200 OK（コード例）** = 公式ドキュメントの実レスポンス例（要素省略は `...` で）
- **呼び出し例** = fetch / SDK の最小実装例（認証ヘッダー込み）

**補足:**
- **このプロジェクトで実際に使うエンドポイントだけ** を抜粋（使わないエンドポイント自体は書かない）
- 採用エンドポイントのパラメータ / フィールドは網羅的に書く（上記「網羅性」参照）
- 表の上に **採用している API バージョン** を必ず明記
- 表とサブセクションの順序を揃える（使用頻度の高い順）
- エラー時の挙動（リトライ可否 / Backoff 戦略）を必ず書く（運用時の事故防止）
