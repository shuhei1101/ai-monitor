# GitHub API

GitHub が提供するリポジトリ / Issue / PR 操作の API。
REST API と GraphQL API の 2 系統があり、ほとんどの操作は REST で行える（コメントの minimize や PR の Ready 化など一部は GraphQL のみ）。

## 現在のバージョン情報

| 項目 | 内容 |
| --- | --- |
| API バージョン | `2022-11-28`（`X-GitHub-Api-Version` ヘッダで指定） |
| ベース URL | `https://api.github.com` |
| 公式 URL | https://docs.github.com/ja/rest |
| 公式ドキュメント | REST: https://docs.github.com/ja/rest / GraphQL: https://docs.github.com/ja/graphql |

## 認証セットアップ

認証方式: Bearer トークン（Personal Access Token）

### 取得手順

1. https://github.com/settings/personal-access-tokens にアクセス
2. `Generate new token`（fine-grained）で対象リポジトリを選び、Repository permissions に `Issues: Read and write` / `Pull requests: Read and write` / `Contents: Read and write` を付与
3. 生成されたトークン（`github_pat_...`）を控える（再表示不可）

### env 変数

```yaml
# ~/.config/ai-monitor/settings.yaml の github_token に設定する
github_token: github_pat_xxxxxxxx
```

### リクエスト時の利用

```bash
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     -H "X-GitHub-Api-Version: 2022-11-28" \
     https://api.github.com/repos/{owner}/{repo}
```

## レートリミット・課金

### レートリミット

| 系統 | 上限 | 補足 |
| --- | --- | --- |
| REST（PAT 認証） | 5,000 リクエスト/時 | 残量は `x-ratelimit-remaining` ヘッダ |
| GraphQL（PAT 認証） | 5,000 ポイント/時 | クエリの複雑さでポイント消費 |
| セカンダリリミット | 短時間の連続書き込みで発動 | `Retry-After` ヘッダに従って待機 |

超過時は HTTP 403 / 429 を返す。
リトライは Exponential Backoff（1s → 2s → 4s）で最大 3 回。

### 課金単価

なし（API 利用は無料。上限はレートリミットのみ）。

## エンドポイント一覧

API バージョン: `2022-11-28`

| METHOD | パス | 用途 | 補足 |
| --- | --- | --- | --- |
| GET | [`/repos/{owner}/{repo}`](#get-reposownerrepo) | リポジトリ情報の取得 | - |
| GET | [`/repos/{owner}/{repo}/issues`](#get-reposownerrepoissues) | Issue / PR 一覧の取得 | open 対象の一括取得に使用 |
| GET | [`/repos/{owner}/{repo}/issues/{issue_number}`](#get-reposownerrepoissuesissue_number) | Issue / PR の取得 | PR も Issue として取れる |
| POST | [`/repos/{owner}/{repo}/issues`](#post-reposownerrepoissues) | Issue の作成 | - |
| PATCH | [`/repos/{owner}/{repo}/issues/{issue_number}`](#patch-reposownerrepoissuesissue_number) | Issue / PR の更新（本文・タイトル・open/close） | - |
| POST | [`/repos/{owner}/{repo}/issues/{issue_number}/labels`](#post-reposownerrepoissuesissue_numberlabels) | ラベルの追加 | - |
| DELETE | [`/repos/{owner}/{repo}/issues/{issue_number}/labels/{name}`](#delete-reposownerrepoissuesissue_numberlabelsname) | ラベルの除去 | - |
| POST | [`/repos/{owner}/{repo}/issues/{issue_number}/assignees`](#post-reposownerrepoissuesissue_numberassignees) | assignee の追加 / 除去 | 除去は同パスの DELETE |
| GET | [`/repos/{owner}/{repo}/issues/{issue_number}/comments`](#get-reposownerrepoissuesissue_numbercomments) | コメント一覧の取得 | - |
| POST | [`/repos/{owner}/{repo}/issues/{issue_number}/comments`](#post-reposownerrepoissuesissue_numbercomments) | コメントの投稿 | - |
| PATCH | [`/repos/{owner}/{repo}/issues/comments/{comment_id}`](#patch-reposownerrepoissuescommentscomment_id) | コメント本文の更新 | - |
| POST | [`/repos/{owner}/{repo}/issues/{issue_number}/sub_issues`](#post-reposownerrepoissuesissue_numbersub_issues) | Sub-issue リンクの付与 | - |
| GET | [`/repos/{owner}/{repo}/issues/{issue_number}/sub_issues`](#get-reposownerrepoissuesissue_numbersub_issues) | Sub-issue の子 Issue 一覧の取得 | - |
| GET | [`/repos/{owner}/{repo}/issues/{issue_number}/parent`](#get-reposownerrepoissuesissue_numberparent) | Sub-issue の親 Issue の取得 | 親なしは 404 |
| POST | [`/repos/{owner}/{repo}/pulls`](#post-reposownerrepopulls) | PR の作成 | Draft 対応 |
| POST | [`/repos/{owner}/{repo}/pulls/{pull_number}/comments`](#post-reposownerrepopullspull_numbercomments) | レビューコメント（インライン）の投稿 | - |
| PUT | [`/repos/{owner}/{repo}/pulls/{pull_number}/merge`](#put-reposownerrepopullspull_numbermerge) | PR のマージ | - |
| DELETE | [`/repos/{owner}/{repo}/git/refs/heads/{branch}`](#delete-reposownerrepogitrefsheadsbranch) | リモートブランチの削除 | - |
| GET | [`/search/issues`](#get-searchissues) | Issue / PR のキーワード横断検索 | 検索レートリミットは別枠 |
| POST | [`/graphql`](#post-graphql) | GraphQL クエリ / mutation の実行 | minimize / Ready 化 等 |

## GET `/repos/{owner}/{repo}`

リポジトリ情報を取得する。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` | `string` | ✅ | - | リポジトリオーナー | - | パスパラメータ |
| `{repo}` | `string` | ✅ | - | リポジトリ名 | - | パスパラメータ |

リクエスト例:

```text
GET /repos/shuhei1101/ai-monitor
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `full_name` | `string` | `owner/name` 形式のリポジトリ名 | - | - |
| `name` | `string` | リポジトリ名 | - | - |
| `default_branch` | `string` | デフォルトブランチ名 | - | - |
| `html_url` | `string` | リポジトリの URL | - | - |

レスポンス例:

```json
{
  "full_name": "shuhei1101/ai-monitor",
  "name": "ai-monitor",
  "default_branch": "master",
  "html_url": "https://github.com/shuhei1101/ai-monitor"
}
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `401` | トークン不正 | - |
| `404` | リポジトリ不存在 / 権限なし | PAT の対象リポジトリ設定を確認 |

## GET `/repos/{owner}/{repo}/issues`

Issue の一覧を取得する（PR も要素として返る。各要素に本文・ラベル・assignee を含む）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` | `string` | ✅ | - | 対象リポジトリ | - | パスパラメータ |
| `state` | `"open"` or `"closed"` or `"all"` | - | `"open"` | 開閉状態のフィルタ | - | query パラメータ |
| `per_page` | `number` | - | `30` | 1 ページの件数 | 最大 100 | query パラメータ |
| `page` | `number` | - | `1` | ページ番号 | - | query パラメータ |

リクエスト例:

```text
GET /repos/shuhei1101/ai-monitor/issues?state=open&per_page=100
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `[].number` | `number` | Issue / PR 番号 | - | - |
| `[].title` | `string` | タイトル | - | - |
| `[].body` | `string` | 本文（Markdown 全文） | - | 未記入は `null` |
| `[].state` | `"open" or "closed"` | 開閉状態 | - | - |
| `[].labels[].name` | `string` | ラベル名 | - | - |
| `[].assignees[].login` | `string` | assignee のログイン名 | - | 未設定は空配列 |
| `[].pull_request` | `object` | PR 情報への参照 | - | Issue（非 PR）では欠落。PR 判定に使える |

レスポンス例:

```json
[
  {
    "number": 52,
    "title": "プロフィール編集 API",
    "body": "## 紐づく Issue\n\n- #50",
    "state": "open",
    "labels": [{ "name": "確認:tester" }],
    "assignees": [],
    "pull_request": { "url": "https://api.github.com/repos/shuhei1101/ai-monitor/pulls/52" }
  }
]
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `404` | リポジトリ不存在 / 権限なし | - |

## GET `/repos/{owner}/{repo}/issues/{issue_number}`

Issue を取得する（PR も同エンドポイントで Issue として取れる。PR 固有情報は `pulls` 側）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` | `string` | ✅ | - | リポジトリオーナー | - | パスパラメータ |
| `{repo}` | `string` | ✅ | - | リポジトリ名 | - | パスパラメータ |
| `{issue_number}` | `number` | ✅ | - | Issue 番号 | - | パスパラメータ |

リクエスト例:

```text
GET /repos/shuhei1101/ai-monitor/issues/35
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `id` | `number` | Issue の REST ID | - | Sub-issue リンクで使う |
| `number` | `number` | Issue 番号 | - | - |
| `node_id` | `string` | GraphQL node_id | - | - |
| `title` | `string` | タイトル | - | - |
| `body` | `string` | 本文（Markdown） | - | 未記入は `null` |
| `state` | `"open" or "closed"` | 開閉状態 | - | - |
| `state_reason` | `"completed" or "not_planned" or "reopened"` | 状態の理由 | - | open で理由なしは `null` |
| `html_url` | `string` | html URL | - | - |
| `labels[].name` | `string` | ラベル名 | - | - |
| `assignees[].login` | `string` | assignee のログイン名 | - | 未設定は空配列 |
| `user.login` | `string` | 起票者のログイン名 | - | - |
| `created_at` | `string` | 作成日時（ISO 8601） | - | - |
| `updated_at` | `string` | 更新日時（ISO 8601） | - | - |
| `closed_at` | `string` | クローズ日時（ISO 8601） | - | open の間は `null` |
| `pull_request` | `object` | PR 情報への参照 | - | Issue（非 PR）では欠落。PR 判定に使える |

レスポンス例:

```json
{
  "id": 3421334455,
  "number": 35,
  "node_id": "I_kwDO...",
  "title": "プロフィール編集機能",
  "state": "open",
  "labels": [{ "name": "layer:epic" }, { "name": "確認:epic-conductor" }],
  "assignees": [],
  "user": { "login": "shuhei1101" },
  "closed_at": null
}
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `404` | Issue 不存在 | - |

## POST `/repos/{owner}/{repo}/issues`

Issue を作成する。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` | `string` | ✅ | - | 対象リポジトリ | - | パスパラメータ |
| `title` | `string` | ✅ | - | タイトル | - | - |
| `body` | `string` | - | `null` | 本文（Markdown） | - | - |
| `labels` | `string[]` | - | `[]` | 付与するラベル名 | - | リポジトリ未定義のラベルは新規作成される |
| `assignees` | `string[]` | - | `[]` | assignee のログイン名 | - | - |

リクエスト例:

```json
{
  "title": "プロフィールを編集する",
  "body": "## 前提条件\n\nなし",
  "labels": ["layer:story", "確認:story-conductor"]
}
```

### レスポンス

作成された Issue オブジェクト（`GET /repos/{owner}/{repo}/issues/{issue_number}` のレスポンスと同形）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `201` | 作成成功 | - |
| `403` | Issues への書き込み権限なし | PAT の permissions を確認 |
| `422` | バリデーション失敗 | - |

## PATCH `/repos/{owner}/{repo}/issues/{issue_number}`

Issue / PR のタイトル・本文・開閉状態を更新する（指定したフィールドだけが変わる）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 対象 Issue | - | パスパラメータ |
| `title` | `string` | - | 変更なし | タイトル | - | - |
| `body` | `string` | - | 変更なし | 本文（完全置換） | - | - |
| `state` | `"open" or "closed"` | - | 変更なし | 開閉状態 | - | reopen は `"open"` を指定 |
| `state_reason` | `"completed" or "not_planned" or "reopened"` | - | `null` | クローズ / 再オープンの理由 | - | `state` とセットで指定 |
| `labels` | `string[]` | - | 変更なし | ラベルの完全置換 | - | 追加 / 除去は専用エンドポイント |
| `assignees` | `string[]` | - | 変更なし | assignee の完全置換 | - | 追加 / 除去は専用エンドポイント |

リクエスト例:

```json
{
  "state": "closed",
  "state_reason": "not_planned"
}
```

### レスポンス

更新後の Issue オブジェクト（`GET /repos/{owner}/{repo}/issues/{issue_number}` のレスポンスと同形）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `403` | 書き込み権限なし | - |
| `422` | バリデーション失敗（`state_reason` の組み合わせ不正 等） | - |

## POST `/repos/{owner}/{repo}/issues/{issue_number}/labels`

ラベルを追加する（既存ラベルは維持・冪等）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 対象 Issue | - | パスパラメータ |
| `labels` | `string[]` | ✅ | - | 追加するラベル名 | - | リポジトリ未定義のラベルは新規作成される（グレー・説明なし。実測確認済み） |

リクエスト例:

```json
{ "labels": ["確認:tester"] }
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `[].name` | `string` | 付与後の全ラベル名 | - | 配列で全件返る |

レスポンス例:

```json
[{ "name": "layer:epic" }, { "name": "確認:tester" }]
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `404` | Issue 不存在 | - |

## DELETE `/repos/{owner}/{repo}/issues/{issue_number}/labels/{name}`

ラベルを 1 つ除去する。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 対象 Issue | - | パスパラメータ |
| `{name}` | `string` | ✅ | - | 除去するラベル名 | - | パスパラメータ（URL エンコードする） |

リクエスト例:

```text
DELETE /repos/shuhei1101/ai-monitor/issues/35/labels/確認:architect
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `[].name` | `string` | 除去後の全ラベル名 | - | - |

レスポンス例:

```json
[{ "name": "layer:epic" }]
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `404` | ラベル未付与 / Issue 不存在 | 未付与のラベルの除去はエラーになる |

## POST `/repos/{owner}/{repo}/issues/{issue_number}/assignees`

assignee を追加する（設定済みは no-op）。
除去は同パスの DELETE（body は同形・200 OK）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 対象 Issue | - | パスパラメータ |
| `assignees` | `string[]` | ✅ | - | 対象のログイン名 | - | 存在しないログイン名は無視される |

リクエスト例:

```json
{ "assignees": ["shuhei1101"] }
```

### レスポンス

更新後の Issue オブジェクト（`GET /repos/{owner}/{repo}/issues/{issue_number}` のレスポンスと同形）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `201` | 追加成功 | DELETE（除去）は `200` |
| `404` | Issue 不存在 | - |

## GET `/repos/{owner}/{repo}/issues/{issue_number}/comments`

コメント一覧を取得する（投稿順・ページネーションあり）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 対象 Issue | - | パスパラメータ |
| `per_page` | `number` | - | `30` | 1 ページの件数 | 最大 100 | query パラメータ |
| `page` | `number` | - | `1` | ページ番号 | - | query パラメータ |

リクエスト例:

```text
GET /repos/shuhei1101/ai-monitor/issues/35/comments?per_page=100
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `[].id` | `number` | コメントの REST ID | - | - |
| `[].node_id` | `string` | GraphQL node_id | - | minimize の対象指定に使う |
| `[].body` | `string` | コメント本文 | - | - |
| `[].user.login` | `string` | 投稿者のログイン名 | - | - |
| `[].created_at` | `string` | 投稿日時（ISO 8601） | - | - |
| `[].html_url` | `string` | コメントの URL | - | - |

レスポンス例:

```json
[
  {
    "id": 123456789,
    "node_id": "IC_kwDO...",
    "body": "> from: @architect\n\n設計 Wiki を更新しました。",
    "user": { "login": "shuhei1101" },
    "created_at": "2026-07-18T00:00:00Z",
    "html_url": "https://github.com/shuhei1101/ai-monitor/issues/35#issuecomment-1"
  }
]
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `404` | Issue 不存在 | - |

## POST `/repos/{owner}/{repo}/issues/{issue_number}/comments`

コメントを投稿する（PR も同エンドポイント）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 対象 Issue / PR | - | パスパラメータ |
| `body` | `string` | ✅ | - | コメント本文（Markdown） | 65,536 文字以内 | - |

リクエスト例:

```json
{ "body": "> from: @architect\n\n設計 Wiki を更新しました。" }
```

### レスポンス

投稿されたコメントオブジェクト（`GET .../comments` の要素と同形）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `201` | 投稿成功 | - |
| `403` | 書き込み権限なし | - |
| `404` | Issue 不存在 | - |

## PATCH `/repos/{owner}/{repo}/issues/comments/{comment_id}`

コメント本文を更新する（完全置換）。
`{comment_id}` は REST ID。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{comment_id}` | - | ✅ | - | 対象コメント | - | パスパラメータ |
| `body` | `string` | ✅ | - | 更新後の本文 | 65,536 文字以内 | - |

リクエスト例:

```json
{ "body": "...\n\n---\n> from: @tester\n\n修正しました。" }
```

### レスポンス

更新後のコメントオブジェクト（`GET .../comments` の要素と同形）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `404` | コメント不存在 | REST ID を確認 |

## POST `/repos/{owner}/{repo}/issues/{issue_number}/sub_issues`

Issue に Sub-issue リンクを付与する（`{issue_number}` が親）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 親 Issue | - | パスパラメータ |
| `sub_issue_id` | `number` | ✅ | - | 子 Issue の **REST ID**（番号ではない） | - | `GET .../issues/{n}` の `id` |

リクエスト例:

```json
{ "sub_issue_id": 3421334455 }
```

### レスポンス

親の Issue オブジェクト（`GET /repos/{owner}/{repo}/issues/{issue_number}` のレスポンスと同形）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `201` | リンク成功 | - |
| `404` | 親 / 子 Issue 不存在 | - |
| `422` | リンク不可（循環 / 上限超過 等） | - |

## GET `/repos/{owner}/{repo}/issues/{issue_number}/sub_issues`

Sub-issue リンクの子 Issue 一覧を取得する（`{issue_number}` が親）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 親 Issue | - | パスパラメータ |
| `per_page` | `number` | - | `30` | 1 ページの件数 | 最大 100 | query パラメータ |
| `page` | `number` | - | `1` | ページ番号 | - | query パラメータ |

リクエスト例:

```text
GET /repos/shuhei1101/ai-monitor/issues/35/sub_issues
```

### レスポンス

子 Issue オブジェクトの配列（要素は `GET /repos/{owner}/{repo}/issues/{issue_number}` のレスポンスと同形）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | 子なしは空配列 |
| `404` | Issue 不存在 | - |

## GET `/repos/{owner}/{repo}/issues/{issue_number}/parent`

Sub-issue リンクの親 Issue を取得する。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{issue_number}` | - | ✅ | - | 子 Issue | - | パスパラメータ |

リクエスト例:

```text
GET /repos/shuhei1101/ai-monitor/issues/36/parent
```

### レスポンス

親の Issue オブジェクト（`GET /repos/{owner}/{repo}/issues/{issue_number}` のレスポンスと同形）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `404` | 親リンクなし / Issue 不存在 | 親なしは 404（実測確認済み） |

## POST `/repos/{owner}/{repo}/pulls`

PR を作成する。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` | - | ✅ | - | 対象リポジトリ | - | パスパラメータ |
| `title` | `string` | ✅ | - | PR タイトル | - | - |
| `body` | `string` | - | `null` | PR 本文 | - | - |
| `head` | `string` | ✅ | - | head ブランチ名 | - | リモート push 済みが前提 |
| `base` | `string` | ✅ | - | マージ先ブランチ名 | - | - |
| `draft` | `boolean` | - | `false` | Draft として作成 | - | - |

リクエスト例:

```json
{
  "title": "プロフィール編集 API",
  "body": "## 紐づく Issue\n\n- #50",
  "head": "feat/backend/profile/edit/edit-api",
  "base": "feat/story/profile/edit",
  "draft": true
}
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `number` | `number` | PR 番号 | - | - |
| `node_id` | `string` | GraphQL node_id | - | Ready 化（GraphQL）で使う |
| `html_url` | `string` | PR の URL | - | - |
| `draft` | `boolean` | Draft かどうか | - | - |
| `state` | `"open" or "closed"` | 開閉状態 | - | - |

レスポンス例:

```json
{
  "number": 52,
  "node_id": "PR_kwDO...",
  "html_url": "https://github.com/shuhei1101/ai-monitor/pull/52",
  "draft": true,
  "state": "open"
}
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `201` | 作成成功 | - |
| `422` | head 不存在 / 同一ブランチ間 / 既存 PR あり | - |

## POST `/repos/{owner}/{repo}/pulls/{pull_number}/comments`

PR の diff 上の特定ファイル・特定行に紐づくレビューコメント（インライン）を投稿する。
会話欄のコメント（`POST .../issues/{issue_number}/comments`）とは別系統のスレッドになる。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{pull_number}` | - | ✅ | - | 対象 PR | - | パスパラメータ |
| `body` | `string` | ✅ | - | コメント本文（Markdown） | 65,536 文字以内 | - |
| `commit_id` | `string` | ✅ | - | 対象 diff の commit SHA | - | 通常は PR の head SHA |
| `path` | `string` | ✅ | - | 対象ファイルパス（リポジトリルート相対） | - | - |
| `line` | `number` | ✅ | - | 対象行番号（範囲指定時は終端行） | diff に含まれる行のみ | - |
| `side` | `"RIGHT" or "LEFT"` | - | `"RIGHT"` | diff のどちら側の行か | - | 追加・文脈行は RIGHT / 削除行は LEFT |
| `start_line` | `number` | - | なし（単一行コメント） | 範囲コメントの開始行 | `line` より小さい行 | 範囲は `start_line`〜`line` |
| `start_side` | `"RIGHT" or "LEFT"` | - | `side` と同じ | 開始行側の diff の side | - | `start_line` 指定時のみ有効 |

リクエスト例:

```json
{
  "body": "> from: @architect\n> to: @implementer\n\nここは null チェックが必要です。",
  "commit_id": "6dcb09b5b57875f334f61aebed695e2e4193db5e",
  "path": "src/ai_monitor/features/agents/service.py",
  "line": 42,
  "side": "RIGHT"
}
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `id` | `number` | レビューコメントの REST ID | - | - |
| `node_id` | `string` | GraphQL node_id | - | `PRRC_` 始まり |
| `html_url` | `string` | コメントの URL | - | - |
| `path` | `string` | 対象ファイルパス | - | - |
| `line` | `number` | 対象行番号 | - | - |

レスポンス例:

```json
{
  "id": 987654321,
  "node_id": "PRRC_kwDO...",
  "html_url": "https://github.com/shuhei1101/ai-monitor/pull/52#discussion_r987654321",
  "path": "src/ai_monitor/features/agents/service.py",
  "line": 42
}
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `201` | 投稿成功 | - |
| `404` | PR 不存在 | - |
| `422` | `line` が diff に含まれない / `commit_id` 不正 | - |

## PUT `/repos/{owner}/{repo}/pulls/{pull_number}/merge`

PR をマージする。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` / `{pull_number}` | - | ✅ | - | 対象 PR | - | パスパラメータ |
| `merge_method` | `"merge" or "squash" or "rebase"` | - | `"merge"` | マージ戦略 | - | - |
| `commit_title` | `string` | - | 自動生成 | マージコミットのタイトル | - | - |

リクエスト例:

```json
{ "merge_method": "squash" }
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `merged` | `boolean` | マージされたか | - | - |
| `sha` | `string` | マージコミットの SHA | - | - |

レスポンス例:

```json
{ "merged": true, "sha": "6dcb09b5b57875f334f61aebed695e2e4193db5e" }
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | マージ成功 | - |
| `405` | マージ不可（コンフリクト / Draft のまま 等） | - |
| `409` | head が変化した | 最新の head SHA で再試行 |

## DELETE `/repos/{owner}/{repo}/git/refs/heads/{branch}`

リモートブランチを削除する。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `{owner}` / `{repo}` | - | ✅ | - | 対象リポジトリ | - | パスパラメータ |
| `{branch}` | `string` | ✅ | - | 削除するブランチ名 | - | パスパラメータ |

リクエスト例:

```text
DELETE /repos/shuhei1101/ai-monitor/git/refs/heads/feat/backend/profile/edit/edit-api
```

### レスポンス

なし（`204 No Content`・ボディなし）。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `204` | 削除成功 | - |
| `422` | ブランチ不存在 / 保護ブランチ | - |

## GET `/search/issues`

キーワードで Issue / PR を横断検索する（githubkit: `rest.search.issues_and_pull_requests`）。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `q` | `string` | ✅ | - | 検索クエリ | OR・正規表現は不可 | query パラメータ。`repo:{owner}/{repo}` で対象リポジトリを絞る。スペース区切りは AND・`"..."` は語順込みのフレーズ一致・`in:title` / `label:` / `is:issue` / `is:pr` / `author:` / `state:` 等の修飾子可 |
| `sort` | `string` | - | なし（関連度順） | 並び順 | `comments` / `reactions` / `reactions-+1` / `reactions--1` / `reactions-smile` / `reactions-thinking_face` / `reactions-heart` / `reactions-tada` / `interactions` / `created` / `updated` | query パラメータ |
| `order` | `string` | - | `desc` | 昇順 / 降順 | `asc` / `desc` | `sort` 指定時のみ有効 |
| `per_page` | `number` | - | `30` | 1 ページの件数 | 最大 100 | query パラメータ |
| `page` | `number` | - | `1` | ページ番号 | - | query パラメータ |

リクエスト例:

```text
GET /search/issues?q=repo:shuhei1101/ai-monitor "プロフィール編集" in:title&sort=created&order=desc
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `total_count` | `number` | ヒット総数 | - | - |
| `incomplete_results` | `boolean` | タイムアウトで結果が打ち切られたか | - | - |
| `items` | `object[]` | 検索結果（`GET /repos/{owner}/{repo}/issues/{issue_number}` のレスポンスと同形） | 先頭 1000 件まで取得可 | PR は `pull_request` フィールドを持つ |

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | 0 件でも `200`（`items` が空配列） |
| `403` | 検索レートリミット超過 | 検索 API は通常のレートリミットと別枠（認証時 30 リクエスト / 分） |
| `422` | クエリ構文エラー | - |

## POST `/graphql`

GraphQL クエリ / mutation を実行する。
REST に存在しない操作はこちらで行う。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `query` | `string` | ✅ | - | GraphQL クエリ / mutation | - | - |
| `variables` | `object` | - | `{}` | クエリ変数 | - | - |

リクエスト例:

```json
{
  "query": "mutation($id: ID!) { minimizeComment(input: { subjectId: $id, classifier: RESOLVED }) { minimizedComment { isMinimized } } }",
  "variables": { "id": "IC_kwDO..." }
}
```

他の代表的なクエリ:

```graphql
# PR の Ready 化（Draft 解除）
mutation($id: ID!) { markPullRequestReadyForReview(input: { pullRequestId: $id }) { pullRequest { isDraft } } }

# コメントの isMinimized 取得
query($id: ID!) { node(id: $id) { ... on IssueComment { isMinimized body } } }

# レビュースレッド（インラインコメント）の解決
mutation($id: ID!) { resolveReviewThread(input: { threadId: $id }) { thread { isResolved } } }

# PR のレビュースレッド一覧
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes { id isResolved path startLine line comments(first: 50) { nodes { id body author { login } createdAt url } } }
      }
    }
  }
}
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `data` | `object` | クエリの selection と同形の結果 | - | - |
| `errors[].message` | `string` | GraphQL エラーの内容 | - | 成功時は `errors` 自体が欠落 |

レスポンス例:

```json
{ "data": { "minimizeComment": { "minimizedComment": { "isMinimized": true } } } }
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常（クエリエラー時も `200` + `errors`） | GraphQL はエラーでも HTTP 200 |
| `401` | トークン不正 | - |
