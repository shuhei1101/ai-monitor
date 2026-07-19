# gh（GitHub CLI）

GitHub 公式のコマンドラインツール。
Issue / PR の操作・REST / GraphQL API の呼び出しをターミナルコマンドとして提供する。

## 現在のバージョン情報

| 項目 | 内容 |
| --- | --- |
| バージョン | `v2.95.0` |
| ライセンス | MIT |
| 公式 URL | https://cli.github.com/ |
| 公式ドキュメント | https://cli.github.com/manual/ |

## インストール手順

```bash
# Ubuntu / WSL
sudo apt install gh

# 認証（初回のみ・ブラウザ連携）
gh auth login
```

- 実行にはリポジトリ内のカレントディレクトリが前提（対象リポジトリを CWD から解決する）
- 認証状態は `gh auth status` で確認できる

## メソッド一覧

バージョン: `v2.95.0`

| 種別 | 名前 | 用途 | 補足 |
| --- | --- | --- | --- |
| コマンド | [`gh issue view` / `gh pr view`](#gh-issue-view) | Issue / PR の情報を JSON で取得 | - |
| コマンド | [`gh issue edit` / `gh pr edit`](#gh-issue-edit) | ラベル・assignee・本文・タイトルの更新 | - |
| コマンド | [`gh issue create`](#gh-issue-create) | Issue の作成 | - |
| コマンド | [`gh issue close` / `gh pr close`](#gh-issue-close) | Issue / PR のクローズ | - |
| コマンド | [`gh issue reopen`](#gh-issue-reopen) | クローズ済み Issue の再オープン | - |
| コマンド | [`gh pr create`](#gh-pr-create) | Draft PR の作成（base 指定） | - |
| コマンド | [`gh pr ready`](#gh-pr-ready) | Draft の解除 | - |
| コマンド | [`gh pr merge`](#gh-pr-merge) | PR のマージ | - |
| コマンド | [`gh api`](#gh-api) | REST / GraphQL API の直接呼び出し | - |

### `gh issue view`

Issue の情報を JSON で取得する。
`gh pr view` も同一フラグ（PR は `mergedAt` 等の PR 固有フィールドを持つ）。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{number}` | `number` | 必須 | - | 対象の Issue / PR 番号 | 位置引数 |
| `--json` | `string` | 必須 | - | 取得するフィールドをカンマ区切りで指定 | 指定なしだと人間向け表示になるため機械処理では必須 |
| `--jq` | `string` | 任意 | なし | 出力に jq 式を適用 | - |

パラメータ例:

```bash
gh issue view 35 --json labels --jq ".labels[].name"
gh issue view 35 --json title,body,labels,assignees,comments
```

#### 戻り値

stdout に JSON で出力される。
`--json` で指定したフィールドだけが含まれる（主要フィールド）。

| フィールド | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `number` | number | Issue / PR 番号 | - |
| `title` | string | タイトル | - |
| `body` | string | 本文（Markdown） | - |
| `url` | string | html URL | - |
| `state` | `"OPEN" or "CLOSED" or "MERGED"` | 開閉状態 | `MERGED` は PR のみ |
| `closed` | boolean | クローズ済みか | - |
| `closedAt?` | string | クローズ日時（ISO 8601） | open の間は `null` |
| `createdAt` | string | 作成日時（ISO 8601） | - |
| `updatedAt` | string | 更新日時（ISO 8601） | - |
| `labels[].name` | string | ラベル名 | `id` / `color` / `description` も返る |
| `assignees[].login` | string | assignee のログイン名 | 未設定は空配列 |
| `author.login` | string | 起票者のログイン名 | - |
| `comments[].id` | string | コメントの GraphQL node_id | - |
| `comments[].body` | string | コメント本文 | - |
| `comments[].createdAt` | string | 投稿日時（ISO 8601） | - |
| `comments[].author.login` | string | 投稿者のログイン名 | - |
| `comments[].url` | string | コメントの html URL | - |
| `comments[].isMinimized` | boolean | Resolve（minimize）済みか | - |
| `parent?.number` | number | Sub-issue リンクの親 Issue 番号 | 親なしは `parent` が `null`。`title` / `url` / `state` も返る |
| `subIssues[].number` | number | Sub-issue リンクの子 Issue 番号 | 子なしは空配列。`title` / `url` / `state` も返る |
| `subIssuesSummary.total` | number | 子 Issue の総数 | - |
| `subIssuesSummary.completed` | number | クローズ済みの子 Issue 数 | - |
| `subIssuesSummary.percentCompleted` | number | 完了率 | - |

戻り値例:

```json
{
  "number": 35,
  "title": "プロフィール編集機能",
  "state": "OPEN",
  "closedAt": null,
  "labels": [{ "name": "layer:epic" }, { "name": "確認:epic-conductor" }],
  "assignees": [{ "login": "shuhei1101" }],
  "comments": [
    { "id": "IC_kwDO...", "body": "> from: @architect...", "isMinimized": false }
  ],
  "parent": { "number": 12 },
  "subIssuesSummary": { "total": 2, "completed": 1, "percentCompleted": 50 }
}
```

### `gh issue edit`

Issue のラベル・assignee・本文・タイトルを更新する。
`gh pr edit` も同一フラグ。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{number}` | `number` | 必須 | - | 対象の Issue / PR 番号 | 位置引数 |
| `--add-label` | `string` | 任意 | なし | ラベルを追加 | 複数指定は繰り返し。リポジトリ未定義のラベルはエラー |
| `--remove-label` | `string` | 任意 | なし | ラベルを除去 | 未付与のラベルは無視される |
| `--add-assignee` | `string` | 任意 | なし | assignee を追加 | 設定済みは no-op |
| `--remove-assignee` | `string` | 任意 | なし | assignee を除去 | 未設定は no-op |
| `--body-file` | `string` | 任意 | なし | 本文をファイルから完全置換（`-` で stdin） | 改行を含む本文はこちら |
| `--title` | `string` | 任意 | なし | タイトルを置換 | - |

パラメータ例:

```bash
gh issue edit 35 --remove-label "確認:architect" --add-label "確認:tester"
echo "新しい本文" | gh issue edit 35 --body-file -
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| stdout（テキスト） | 対象の URL | - |

戻り値例:

```text
https://github.com/shuhei1101/ai-monitor/issues/35
```

### `gh issue create`

Issue を作成する。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `--title` | `string` | 必須 | - | タイトル | - |
| `--body` | `string` | 必須 | - | 本文 | - |
| `--label` | `string` | 任意 | なし | 付与するラベル | 複数指定は繰り返し |

パラメータ例:

```bash
gh issue create --title "プロフィールを編集する" --body "..." --label "layer:story" --label "確認:story-conductor"
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| stdout（テキスト） | 作成した Issue の URL（最終行） | - |

戻り値例:

```text
https://github.com/shuhei1101/ai-monitor/issues/36
```

### `gh issue close`

Issue をクローズする。
`gh pr close` は PR 用（`--reason` の代わりに `--delete-branch` を持つ）。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{number}` | `number` | 必須 | - | 対象の番号 | 位置引数 |
| `--reason` | `"completed" or "not planned"` | 任意 | `"completed"` | クローズ理由 | Issue のみ |
| `--delete-branch` | `flag` | 任意 | `false` | head ブランチを同時に削除 | PR（`gh pr close`）のみ |

パラメータ例:

```bash
gh issue close 35 --reason "not planned"
gh pr close 60 --delete-branch
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| stdout（テキスト） | クローズ結果のメッセージ | - |

戻り値例:

```text
✓ Closed issue #35
```

### `gh issue reopen`

クローズ済みの Issue を再オープンする（open 済みの番号を指定するとエラー）。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{number}` | `number` | 必須 | - | 対象の Issue 番号 | 位置引数 |

パラメータ例:

```bash
gh issue reopen 50
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| stdout（テキスト） | 再オープン結果のメッセージ | - |

戻り値例:

```text
✓ Reopened issue #50
```

### `gh pr create`

PR を作成する（Stacked PR は `--base` で親ブランチを指定）。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `--draft` | `flag` | 任意 | `false` | Draft として作成 | - |
| `--base` | `string` | 任意 | デフォルトブランチ | マージ先ブランチ | - |
| `--head` | `string` | 任意 | カレントブランチ | head ブランチ | リモート push 済みが前提 |
| `--title` | `string` | 必須 | - | PR タイトル | - |
| `--body` | `string` | 必須 | - | PR 本文 | - |

パラメータ例:

```bash
gh pr create --draft --base feat/story/profile/edit --head feat/backend/profile/edit/edit-api --title "プロフィール編集 API" --body "..."
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| stdout（テキスト） | 作成した PR の URL（最終行） | - |

戻り値例:

```text
https://github.com/shuhei1101/ai-monitor/pull/52
```

### `gh pr ready`

Draft PR を Ready 化する（Ready 済みの番号を指定するとエラー）。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{number}` | `number` | 必須 | - | 対象の PR 番号 | 位置引数 |

パラメータ例:

```bash
gh pr ready 52
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| stdout（テキスト） | Ready 化結果のメッセージ | - |

戻り値例:

```text
✓ Pull request #52 is marked as "ready for review"
```

### `gh pr merge`

PR をマージする（コンフリクト・マージ不可の状態ではエラー）。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{number}` | `number` | 必須 | - | 対象の PR 番号 | 位置引数 |
| `--squash` | `flag` | ※1 | - | squash マージ | - |
| `--merge` | `flag` | ※1 | - | マージコミット | - |
| `--rebase` | `flag` | ※1 | - | rebase マージ | - |
| `--delete-branch` | `flag` | 任意 | `false` | マージ後にブランチを削除 | - |

※1: 3 つのうちいずれか 1 つを指定する。

パラメータ例:

```bash
gh pr merge 52 --squash --delete-branch
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| stdout（テキスト） | マージ結果のメッセージ | - |

戻り値例:

```text
✓ Squashed and merged pull request #52
```

### `gh api`

GitHub の REST / GraphQL API を直接呼び出す（サブコマンドにない操作用）。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{endpoint}` | `string` | 必須 | - | REST パス or `graphql` | 位置引数 |
| `-f` | `string` | 任意 | なし | リクエストフィールド（`key=value`・文字列） | 複数指定は繰り返し。GraphQL のクエリ・変数もこれで渡す |
| `-F` | `string` | 任意 | なし | 型付きフィールド（数値 / bool / `@file`） | - |
| `--jq` | `string` | 任意 | なし | 出力に jq 式を適用 | - |

パラメータ例:

```bash
# REST: コメント投稿
gh api "repos/{owner}/{repo}/issues/35/comments" -f body="こんにちは" --jq "{node_id, html_url}"

# GraphQL: コメント Resolve
gh api graphql -f query='mutation($id: ID!) { minimizeComment(input: { subjectId: $id, classifier: RESOLVED }) { minimizedComment { isMinimized } } }' -f id="IC_kwDO..."
```

#### 戻り値

stdout に呼び出した API のレスポンス JSON がそのまま出力される。
代表的な呼び出しの主要フィールド:

**コメント投稿（REST `repos/{owner}/{repo}/issues/{n}/comments`）:**

| フィールド | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `id` | number | コメントの REST ID | - |
| `node_id` | string | コメントの GraphQL node_id | Resolve / 返信の対象指定に使う |
| `html_url` | string | コメントの URL | - |
| `body` | string | 投稿した本文 | - |
| `user.login` | string | 投稿者のログイン名 | - |
| `created_at` | string | 投稿日時（ISO 8601） | REST は snake_case |

**GraphQL（`gh api graphql`）:**

| フィールド | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `data` | object | クエリ / mutation の実行結果 | 中身は投げたクエリの selection と同じ形 |
| `errors?[].message` | string | GraphQL エラーの内容 | 成功時は `errors` 自体が欠落 |

戻り値例:

```json
{ "node_id": "IC_kwDO...", "html_url": "https://github.com/.../issues/35#issuecomment-1" }
```

```json
{ "data": { "minimizeComment": { "minimizedComment": { "isMinimized": true } } } }
```
