---
template_version: 1.2.0
---

# GitHub API

GitHub が提供するリポジトリ / Issue / PR 操作の API。
REST API と GraphQL API の 2 系統があり、ほとんどの操作は REST で行える（コメントの minimize や PR の Ready 化など一部は GraphQL のみ）。

## 現在のバージョン情報

| 項目 | 内容 | 補足 |
| --- | --- | --- |
| API バージョン | `2022-11-28`（`X-GitHub-Api-Version` ヘッダで指定） | 2026-07-24 時点最新 |
| ベース URL | `https://api.github.com` | - |
| 公式 URL | https://docs.github.com/ja/rest | - |
| 公式ドキュメント | REST: https://docs.github.com/ja/rest / GraphQL: https://docs.github.com/ja/graphql | - |

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
| POST | [`/repos/{owner}/{repo}/stacks`](#post-reposownerrepostacks) | PR スタックの作成 | public preview（2026-07-30 開始） |
| GET | [`/repos/{owner}/{repo}/stacks/{stack_number}`](#get-reposownerrepostacksstack_number) | PR スタックの取得 | 解散済みは 404 |
| POST | [`/repos/{owner}/{repo}/stacks/{stack_number}/add`](#post-reposownerrepostacksstack_numberadd) | スタック上端への PR 追加 | - |
| POST | [`/repos/{owner}/{repo}/stacks/{stack_number}/unstack`](#post-reposownerrepostacksstack_numberunstack) | スタックの解除 | 1 件指定でもスタック全体が解散する |
| PUT | [`/repos/{owner}/{repo}/pulls/{pull_number}/merge-async`](#put-reposownerrepopullspull_numbermerge-async) | 非同期マージ | スタック内の PR はこちらでしかマージできない |

## 不具合一覧

| タイトル | 概要 | 発生日 |
| --- | --- | --- |
| [レビューコメントが Files changed に出ない](#レビューコメントが-files-changed-に出ない) | API も HTML も正常なのに、新しい Files changed 体験が有効なアカウントでだけ表示されない | 2026/08/02 |
| [対象行が後続 commit で変わるとレビューコメントが Files changed から外れる](#対象行が後続-commit-で変わるとレビューコメントが-files-changed-から外れる) | GitHub が outdated と判定し、Conversation にしか残らなくなる | 2026/08/02 |

### レビューコメントが Files changed に出ない

> 発生日: 2026/08/02

**概要:**

`POST /repos/{owner}/{repo}/pulls/{pull_number}/comments` で投稿したレビューコメントが、Files changed タブに 1 件も表示されない。
Conversation タブには表示される。

API 上は正常で、`commit_id` が PR の head と一致し、`line` / `position` とも非 null、GraphQL の `isResolved` / `isOutdated` / `isCollapsed` はすべて false になる。

サーバーが返す HTML も正しい。
`https://github.com/{owner}/{repo}/pull/{n}/files` を取得すると、diff の各行の直後に `js-inline-comments-container` としてコメントが正しい行番号で埋め込まれている（`blob-code` の行も全て揃い、遅延ロードの省略もない）。
つまり API・HTML とも問題はなく、ブラウザ側の描画だけが欠ける。

同じ PR を未ログイン（シークレットウィンドウ）で開くと表示される。
ログイン済みアカウントでは、別タブ・スーパーリロード・時間経過（3 時間以上）のいずれでも表示されない。

**条件:**

- ログイン済みのアカウントで、新しい Files changed 体験が有効になっている（2026/01/22 から段階的にロールアウト中）
- 未ログイン（シークレットウィンドウ）では再現しない

アカウント単位の機能フラグで UI が切り替わるため、ブラウザのキャッシュ削除やスーパーリロードでは変わらない。
ブラウザ拡張機能の干渉ではない（拡張を入れていない環境でも再現する）。

**対処法:**

| 方法 | 結果 | 推奨 |
| --- | --- | --- |
| Files changed 上部の Preview メニューから従来の UI に戻す | 表示される。アカウント単位で切り替わるため以降も継続する | ○ |
| シークレットウィンドウで開く | 表示される。ログインが要る操作（返信・Resolve）ができない | - |
| Conversation タブで読む | 指摘は読めるが、コードと並べて見られない | - |

### 対象行が後続 commit で変わるとレビューコメントが Files changed から外れる

> 発生日: 2026/08/02

**概要:**

コメントを付けた行が後続の commit で変更されると、GitHub がそのコメントを outdated と判定し、Files changed タブから外す。
レスポンスの `line` が `null` になり（`original_line` は残る）、GraphQL の `isOutdated` が true になる。
Conversation タブには「Outdated」付きで残る。

変更されていない行に付けたコメントは push 後も残るため、消えるのは自分が指摘した行を自分で書き換えた場合にあたる。

**条件:**

- コメントを投稿した後、その行を含む変更を push した
- `subject_type` が `file` のファイルレベルコメントは、ファイルが変更されていなくても push だけで outdated になる

**対処法:**

| 方法 | 結果 | 推奨 |
| --- | --- | --- |
| 指摘が残っているうちに対応し、解決したらスレッドを Resolve する | 未解決のまま消える状態を避けられる。既に消えたものは戻らない | ○ |
| 最新の行に同じ指摘を投稿し直す | Files changed で読めるようになるが、元スレッドの往復履歴が分断される | - |
| `subject_type: "file"` に切り替える | 行に紐づかなくなるが、push のたびに全件 outdated になるため悪化する | - |

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
        nodes { id isResolved path startLine line comments(first: 50) { nodes { id body diffHunk author { login } createdAt url } } }
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

## POST `/repos/{owner}/{repo}/stacks`

複数の PR を Stacked Pull Requests として繋ぐ。

public preview の機能（2026-07-30 提供開始）。
`pull_requests` は下（base ブランチに近い側）から上への順で渡し、各 PR の base ref が直前の PR の head ref と一致している必要がある。

スタックの底は必ずしもデフォルトブランチを base にしなくてよい（`base: {"ref": "任意のブランチ"}` のスタックが作れる）。
ただし `gh stack link` 経由で作ると CLI が底の base をデフォルトブランチへ書き換えるため、base を保ちたい場合は本 API を直接呼ぶ。

1 つの PR が同時に属せるスタックは 1 つだけで、既にスタックに属している PR を別のスタックへ入れようとすると `Pull request #N is already part of a stack` で失敗する。
そのため 1 つの親から複数の子が枝分かれする木構造は、分岐点の PR を含む形では表現できない。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `pull_requests` | `number[]` | ✅ | - | スタックを構成する PR 番号を下から上の順に並べたもの | 2 件以上・同一リポジトリ内 | cross-fork は非対応 |

リクエスト例:

```json
{ "pull_requests": [1470, 1472] }
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `number` | `number` | スタック番号 | - | PR / Issue と同じ採番空間を共有する |
| `base.ref` | `string` | スタック全体の base ブランチ | - | 底の PR の base |
| `open` | `boolean` | スタックが有効か | - | - |
| `pull_requests[].number` | `number` | 構成する PR の番号 | - | 下から上の順 |

レスポンス例:

```json
{ "number": 1473, "base": { "ref": "st-e" }, "open": true, "pull_requests": [{ "number": 1470 }, { "number": 1472 }] }
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `201` | 正常 | - |
| `422` | base ref の連鎖が繋がっていない / 既に別スタックに属する PR を含む / 要素が 1 件 | メッセージに理由が入る |

## GET `/repos/{owner}/{repo}/stacks/{stack_number}`

スタックの構成を取得する。

解散済み（`unstack` 済み）のスタック番号は 404 になる。
PR 側から所属を引く場合は GraphQL の `PullRequest.stack`（`number` / `size` / `baseRefName`）と `PullRequest.stackEntry`（`position`）を使う。

### リクエスト

パスパラメータのみ。

```
GET /repos/{owner}/{repo}/stacks/{stack_number}
```

### レスポンス

`POST /repos/{owner}/{repo}/stacks` のレスポンスと同形。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `404` | スタックが存在しない / 解散済み | - |

## POST `/repos/{owner}/{repo}/stacks/{stack_number}/add`

既存スタックの上端へ PR を積む。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `pull_requests` | `number[]` | ✅ | - | 現在の上端から上へ積む PR 番号を順に並べたもの | 既存スタックの上端と base ref が繋がっていること | - |

リクエスト例:

```json
{ "pull_requests": [1479] }
```

### レスポンス

`POST /repos/{owner}/{repo}/stacks` のレスポンスと同形。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 正常 | - |
| `422` | base ref が繋がっていない / 既に別スタックに属する PR を含む | - |

## POST `/repos/{owner}/{repo}/stacks/{stack_number}/unstack`

スタックを解除する。

`pull_requests` に 1 件だけ指定しても、残りが 2 件以上あってもスタック自体が解散し、以降そのスタック番号は 404 になる（構成する全 PR の `stack` が `null` になる）。
「一部の PR だけをスタックから外して残りを維持する」ことはできない。

解除しても各 PR の base ref は書き換わらないため、解除 → マージ → 残りを `POST /repos/{owner}/{repo}/stacks` で組み直す、という運用は成立する。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `pull_requests` | `number[]` | ✅ | - | 解除の対象として渡す PR 番号 | - | 何を渡してもスタック全体が解散する |

リクエスト例:

```json
{ "pull_requests": [1479] }
```

### レスポンス

本文なし。

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `204` | 正常 | - |
| `404` | スタックが存在しない / 解散済み | - |

## PUT `/repos/{owner}/{repo}/pulls/{pull_number}/merge-async`

PR をバックグラウンドでマージする。

スタックに属している PR は通常の `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge` では失敗し（`This pull request is part of a stack and must be merged using the asynchronous merge REST API`）、こちらを使う必要がある。

指定した PR より下の未マージ PR は必ず一緒にマージされる。
公式ドキュメント（[Merging stacked pull requests](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-stacked-pull-requests) の `Merging from the bottom up`）に次のとおり明記されている。

- `You cannot merge a mid-stack pull request in isolation, the pull requests below it will always merge with it.`
- `You can merge any number of pull requests at once, as long as they form a contiguous group starting from the lowest unmerged pull request.`
- `The selected pull request and all unmerged pull requests below it land on the base branch together as a single operation.`

`merge_action` は直接マージするかマージキューに載せるかの選択で、下位を巻き込むかどうかは変えられない。
上の PR だけを自分の base ブランチへマージしたい場合は、先に `unstack` でスタックを解除する必要がある。

スタックに属していない PR にも使えるが、その場合は通常の `merge` で足りる。

auto-merge はスタックされた PR では非対応。

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `merge_method` | `"merge" or "squash" or "rebase"` | - | `merge` | マージ方式 | - | `merge`=マージコミット / `squash`=1 コミットに畳む / `rebase`=リベース |
| `merge_action` | `"default" or "direct_merge" or "merge_queue"` | - | `default` | マージの実行方法 | - | `default`=直接マージかキュー投入を自動選択 / `direct_merge`=直接マージ / `merge_queue`=キュー投入 |
| `commit_title` | `string` | - | 自動生成 | マージコミットのタイトル | - | - |
| `commit_message` | `string` | - | 自動生成 | マージコミットの本文 | - | - |
| `sha` | `string` | - | - | head がこの SHA と一致する場合だけマージする | - | 競合検知に使う |

リクエスト例:

```json
{ "merge_method": "squash" }
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `status` | `"pending" or "merged" or "enqueued" or "failed"` | 受付結果 | - | `pending`=処理中 / `merged`=完了 / `enqueued`=マージキュー投入 / `failed`=失敗 |
| `details.uuid` | `string` | 結果取得用の ID | - | `GET /repos/{owner}/{repo}/pulls/{pull_number}/merge-async/{uuid}` で状態を引く |
| `details.message` | `string` | 状態の説明 | - | 失敗理由もここに入る |
| `details.expected_head_sha` | `string` | マージ対象の head SHA | - | - |

レスポンス例:

```json
{ "status": "pending", "details": { "message": "Merge request enqueued.", "uuid": "ad676109-4d57-4466-a866-d881100eb9a1", "merge_method": "squash", "merge_action": "default" } }
```

### ステータスコード

| ステータスコード | 発生条件 | 補足 |
| --- | --- | --- |
| `200` | 既にマージ済み / キュー投入済み | - |
| `202` | 受付（バックグラウンドで処理） | `uuid` でポーリングする |
| `400` | マージできる状態にない | Draft のまま・下位 PR が Draft 等 |
| `409` | 既に別のマージ要求が走っている | - |
