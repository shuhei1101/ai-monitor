---
template_version: 1.0.0
---

# worktree削除

MCP ツール: `worktree_remove`

worktree とローカルブランチを両方削除する（ブランチは強制削除 = `git branch -D` 相当。squash マージ運用では base の履歴に元 commit が残らず通常削除は拒否されるため、恒久記録は closed / merged PR の diff が担う）。
マージ後・PoC close 後・リセットの後片付けはこのツールを使う。

操作対象のリポジトリは、リクエストヘッダから解決した監視対象プロジェクトの作業ディレクトリ。
MCP はモニターと同一プロセスに常駐するため、プロセスの作業ディレクトリ（ai-monitor のクローン）とは一致しない。

- 対応テストファイル: `tests/integration/mcp/test_worktree_remove.py`

## インターフェース

### リクエスト

| パラメータ | 型 | 必須 | デフォルト | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- | --- | --- |
| `branch` | str | ✅ | - | 削除対象のブランチ名 | - | 対応する worktree も削除される |

リクエスト例:

```json
{
  "branch": "feat/backend/profile/edit/edit-api"
}
```

### レスポンス

| フィールド | 型 | 説明 | 制限 | 補足 |
| --- | --- | --- | --- | --- |
| `branch` | str | 削除対象のブランチ名 | - | - |
| `worktree_path` | str | 削除した worktree の絶対パス | - | 対象プロジェクト配下 |

レスポンス例:

```json
{
  "branch": "feat/backend/profile/edit/edit-api",
  "worktree_path": "/path/to/monitored-project/.claude/worktrees/feat-backend-profile-edit-edit-api"
}
```

## 制約

| 項目 | 制約 | 補足 |
| --- | --- | --- |
| タイムアウト | 制限なし | - |
| 対象リポジトリ | ヘッダで解決した監視対象プロジェクトの作業ディレクトリに限る | 解決できない場合は 異常系（プロジェクト不明） |

## フロー一覧

| 分類 | フロー名 | 概要 | 補足 |
| --- | --- | --- | --- |
| 正常 | 正常系 | worktree 削除 → ブランチ強制削除 | - |
| 異常 | 異常系（git 実行失敗） | worktree 不存在 | - |
| 異常 | 異常系（プロジェクト不明） | ヘッダのプロジェクトが設定に無い | 誤ったリポジトリを操作しないための防壁 |

## 正常系

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（テスト用に一時作成した git リポジトリで実行） | - |
| 監視対象プロジェクト | 一時 git リポジトリを `local_path` として設定に登録 | MCP プロセスの作業ディレクトリとは別の場所 |
| 対象 | squash マージ済みのブランチと worktree が存在 | base の履歴に元 commit は残っていない |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール worktree_remove
  participant G as git

  A->>T: branch
  T-->>T: ヘッダから対象プロジェクトを解決
  T->>G: 対象プロジェクトで worktree を削除
  T->>G: 対象プロジェクトで<br>ブランチを強制削除
  T-->>A: branch, worktree_path
```

### 期待値

- 監視対象プロジェクトのリポジトリで worktree とローカルブランチが両方削除されている
- `worktree_path` が監視対象プロジェクトの `local_path` 配下を指している

## 異常系（git 実行失敗）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（テスト用に一時作成した git リポジトリで実行） | - |
| 監視対象プロジェクト | 一時 git リポジトリを `local_path` として設定に登録 | - |
| 入力 | worktree が存在しないブランチ名を指定して呼び出す | git の非 0 終了を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール worktree_remove
  participant G as git

  A->>T: branch（worktree 不存在）
  T-->>T: ヘッダから対象プロジェクトを解決
  T->>G: 対象プロジェクトで worktree を削除
  G-->>T: 非 0 終了
  T-->>A: MCP ツールエラーとして返却
```

### 期待値

- MCP ツールエラーが返る（git の stderr を含む）

## 異常系（プロジェクト不明）

### セットアップ

| セットアップ | 説明 | 補足 |
| --- | --- | --- |
| Mock | なし（テスト用に一時作成した git リポジトリで実行） | - |
| リクエストヘッダ | 設定に存在しないプロジェクト名を指定する | プロジェクト解決の失敗を決定的に誘発 |

### フロー

```mermaid
sequenceDiagram
  participant A as エージェント
  participant T as MCP ツール worktree_remove
  participant G as git

  A->>T: branch（未登録のプロジェクト）
  T-->>T: ヘッダから対象プロジェクトを解決できない
  T-->>A: MCP ツールエラーとして返却
```

### 期待値

- MCP ツールエラーが返る
- git が一度も実行されていない（どのリポジトリの worktree・ブランチも削除されていない）
