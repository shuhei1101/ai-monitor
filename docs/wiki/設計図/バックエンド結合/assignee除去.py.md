# assignee除去

MCP ツール: `remove_assignee`

Issue / PR から現在の認証ユーザーの assignee を除去する。
エージェント起動条件が「assignee にユーザーが未設定」のため、通常はユーザー自身が外すが、リセット等の巻き戻しでエージェントが外す場合はこのツールを使う。

- 対応テストファイル: `tests/integration/mcp/test_remove_assignee.py`

## インターフェース

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `number` | int | ✅ | - | 対象の Issue / PR 番号 | - | - |
| `is_pr` | bool | ✅ | - | PR なら `True` | - | - |

リクエスト例:

```json
{
  "number": 35,
  "is_pr": false
}
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `assignees` | list[str] | 操作後の assignee ログイン名一覧 | - | 空配列 = 未設定 |

レスポンス例:

```json
{
  "assignees": []
}
```

## 制約

| 項目 | 制約 | 補足 |
| --- | --- | --- |
| タイムアウト | 制限なし | - |
| 対象ユーザー | 現在の認証ユーザー（`github_token` の持ち主）のみ | - |

## フロー一覧

| 分類 | フロー名 | 概要 | 補足 |
| --- | --- | --- | --- |
| 正常 | 正常系 | 認証ユーザーの解決 → assignee 除去 → 現況再取得 | - |
| 正常 | 正常系（対象が未設定時） | 未設定の除去は no-op で現況を返す | 冪等 |
| 異常 | 異常系（API エラー） | 認証切れ / 対象不存在 / ネットワーク断 | - |

## 正常系

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API を差し替え（正常応答を返す） | - |
| 対象 Issue / PR | 認証ユーザーが assignee 設定済み | - |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール remove_assignee
  participant GH as GitHub

  A->>T: number, is_pr
  T-->>GH: 認証ユーザーのログイン名を照会
  T->>GH: 解決したログイン名の assignee を除去
  T-->>GH: 操作後の assignee 一覧を再取得
  T-->>A: assignees
```

### 期待値

- 現在の認証ユーザーが assignee から外れている
- 戻り値 `assignees` が除去後の一覧と一致している

## 正常系（対象が未設定時）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API を差し替え（正常応答を返す） | - |
| 対象 Issue / PR | 認証ユーザーが assignee に未設定 | no-op を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール remove_assignee
  participant GH as GitHub

  A->>T: number, is_pr
  T-->>GH: 認証ユーザーのログイン名を照会
  T->>GH: 未設定のログイン名を除去<br>（no-op で受理）
  T-->>GH: 操作後の assignee 一覧を再取得
  T-->>A: assignees（変化なし）
```

### 期待値

- MCP ツールエラーにならず正常終了する（冪等）
- 戻り値 `assignees` が呼び出し前と同じ一覧のまま

## 異常系（API エラー）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API を差し替え（4xx / 5xx を返す） | - |
| 入力 | 存在しない番号を指定して呼び出す | API エラーを決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール remove_assignee
  participant GH as GitHub

  A->>T: number（存在しない番号）, is_pr
  T->>GH: assignee を除去
  GH-->>T: 4xx / 5xx / ネットワーク断
  T-->>A: MCP ツールエラーとして返却
```

### 期待値

- MCP ツールエラーが返る（HTTP ステータスと本文を含む）
- 対象の assignee は変化していない
