# githubkit

GitHub API の型付き Python クライアント。
OpenAPI 定義から生成された REST 呼び出しと GraphQL 実行を 1 クライアントで提供する（sync / async 両対応）。

## 現在のバージョン情報

| 項目 | 内容 |
| --- | --- |
| バージョン | `v0.16.0` |
| ライセンス | MIT |
| 公式 URL | https://github.com/yanyongyu/githubkit |
| 公式ドキュメント | https://github.com/yanyongyu/githubkit#readme |

## インストール手順

```bash
uv add githubkit==0.16.0
```

- 認証はトークン文字列（PAT）をコンストラクタに渡す（fine-grained PAT に対象リポジトリの Issues / Pull requests / Contents の RW を付与）

## メソッド一覧

バージョン: `v0.16.0`

| 種別 | 名前 | 用途 | 補足 |
| --- | --- | --- | --- |
| クラス | [`GitHub`](#github) | クライアント生成（トークン認証） | - |
| メソッド | [`rest.{resource}.{operation}`](#restresourceoperation) | REST API の呼び出し | 型付きレスポンス |
| メソッド | [`graphql()`](#graphql) | GraphQL クエリ / mutation の実行 | minimizeComment 等 |
| メソッド | [`rest.paginate()`](#restpaginate) | ページネーションの自動処理 | - |

### `GitHub`

クライアント本体。
トークン文字列を渡すと Token 認証になる。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `auth` | `str or AuthStrategy` | 任意 | `None`（未認証） | PAT 文字列 or 認証ストラテジー | - |
| `base_url` | `str` | 任意 | `https://api.github.com` | API のベース URL | GitHub Enterprise 用 |
| `timeout` | `float` | 任意 | `None`（無制限） | リクエストタイムアウト（秒） | - |

パラメータ例:

```python
import os
from githubkit import GitHub

gh = GitHub(os.environ["GITHUB_TOKEN"])
```

### `rest.{resource}.{operation}`

REST API の呼び出し。
リソース名前空間（`issues` / `pulls` / `repos` 等）× 操作名で呼び、引数は API のフィールドと同名のキーワード引数。
async 版は `async_{operation}`。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `owner` | `str` | 必須 | - | リポジトリオーナー | - |
| `repo` | `str` | 必須 | - | リポジトリ名 | - |
| `**kwargs` | 操作ごと | 操作ごと | - | API のリクエストフィールドと同名のキーワード引数 | 各操作のフィールドは公式 REST リファレンス参照 |

パラメータ例:

```python
resp = gh.rest.issues.get(owner="shuhei1101", repo="ai-monitor", issue_number=35)
gh.rest.issues.update(owner="shuhei1101", repo="ai-monitor", issue_number=35, labels=["確認:tester"])
gh.rest.pulls.create(owner="shuhei1101", repo="ai-monitor", base="master", head="feat/epic/profile", title="...", body="...", draft=True)
```

#### 戻り値

| フィールド | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `parsed_data` | 操作ごとの生成モデル | 型付きのレスポンスボディ | 属性アクセスできる |
| `status_code` | int | HTTP ステータスコード | - |

戻り値例:

```python
issue = resp.parsed_data
issue.number        # 35
issue.labels[0].name  # "layer:epic"
```

### `graphql()`

GraphQL のクエリ / mutation を実行する。
async 版は `async_graphql`。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `query` | `str` | 必須 | - | GraphQL クエリ / mutation | - |
| `variables` | `dict` | 任意 | `None` | クエリ変数 | - |

パラメータ例:

```python
gh.graphql(
    "mutation($id: ID!) { minimizeComment(input: { subjectId: $id, classifier: RESOLVED }) { minimizedComment { isMinimized } } }",
    {"id": "IC_kwDO..."},
)
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `dict` | `data` の中身（クエリの selection と同形の辞書） | エラー時は `GraphQLFailed` を raise |

戻り値例:

```python
{"minimizeComment": {"minimizedComment": {"isMinimized": True}}}
```

### `rest.paginate()`

ページネーションを自動処理して全要素をイテレートする。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{operation}` | REST 操作 | 必須 | - | 対象の list 系操作（位置引数） | - |
| `**kwargs` | 操作ごと | 操作ごと | - | 対象操作に渡すキーワード引数 | - |

パラメータ例:

```python
for comment in gh.rest.paginate(gh.rest.issues.list_comments, owner="shuhei1101", repo="ai-monitor", issue_number=35):
    print(comment.body)
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `Iterator[T]` | ページを跨いで要素を順に返す | `T` は対象操作の要素モデル |
