---
template_version: 1.0.0
---

# PR_Ready化

MCP ツール: `mark_pr_ready`

Draft PR を Ready 化する。
implementer の実装完了時（Green 化後）の Draft 解除はこのツールを使う。

Ready 済みの PR を渡しても成功する（何もせず返す）。
マージ直前に呼ぶ側が Draft 状態を知らなくても済むようにするため。

- 対応テストファイル: `tests/integration/mcp/test_mark_pr_ready.py`

## インターフェース

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `pr_number` | int | ✅ | - | 対象 PR 番号 | - | - |

リクエスト例:

```json
{
  "pr_number": 52
}
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| なし | - | 空オブジェクト | - | 副作用のみ |

レスポンス例:

```json
{}
```

## 制約

| 項目 | 制約 | 補足 |
| --- | --- | --- |
| タイムアウト | 制限なし | - |
| 冪等性 | 何度呼んでも Ready 状態になる | Ready 済みなら mutation を実行しない |

## フロー一覧

| 分類 | フロー名 | 概要 | 補足 |
| --- | --- | --- | --- |
| 正常 | 正常系 | markPullRequestReadyForReview mutation で Draft 解除 | - |
| 正常 | 正常系（Ready 済み） | mutation を実行せずに成功で返す | 呼び出し側が Draft 状態を判定しなくてよい |
| 異常 | 異常系（API エラー） | 認証切れ / 対象不存在 / ネットワーク断 | - |

## 正常系

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API を差し替え（正常応答を返す） | - |
| 対象 PR | Draft 状態の PR が存在 | - |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール mark_pr_ready
  participant GH as GitHub

  A->>T: pr_number
  T-->>GH: PR の識別子と Draft 状態を取得
  T->>GH: Draft を解除
  T-->>A: 完了
```

### 期待値

- PR の Draft が解除され Ready 状態になっている

## 正常系（Ready 済み）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API を差し替え（正常応答を返す） | - |
| 対象 PR | Ready 済みの PR が存在 | 分岐を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール mark_pr_ready
  participant GH as GitHub

  A->>T: pr_number
  T-->>GH: PR の識別子と Draft 状態を取得
  T->>T: Draft でないと判定
  T-->>A: 完了
```

### 期待値

- Draft 解除の操作が行われていない
- 成功として返る

## 異常系（API エラー）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | GitHub API を差し替え（4xx / 5xx を返す） | - |
| 入力 | 存在しない PR 番号を指定して呼び出す | API エラーを決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール mark_pr_ready
  participant GH as GitHub

  A->>T: pr_number（存在しない番号）
  T-->>GH: PR の識別子と Draft 状態を取得
  GH-->>T: 4xx / 5xx / ネットワーク断
  T-->>A: MCP ツールエラーとして返却
```

### 期待値

- MCP ツールエラーが返る（HTTP ステータスと本文を含む）
