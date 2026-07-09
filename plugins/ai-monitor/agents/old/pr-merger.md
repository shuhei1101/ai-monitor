---
name: pr-merger
description: 確認:pr-merger ラベル付き PR を 1 件マージし、worktree 削除まで実行
model: sonnet
---

`ai-monitor:pr-merge` スキルに処理を委譲する薄ラッパー。
スキル実行完了後、下記戻り値 JSON を呼び出し元へ返す。

## 入力

| 引数 | 内容 |
| --- | --- |
| PR 番号 | 例: 42 |
| ベースブランチ | 例: `master` |
| ヘッドブランチ | 例: `feat/foo-bar` |
| リポジトリ root | メインリポジトリの絶対パス |

## タスク

受け取った引数をそのまま `/ai-monitor:pr-merge` スキルに渡して実行する。

## 戻り値

スキル実行完了後、以下の JSON を呼び出し元に返す:

```json
{
  "verdict": "merged" | "conflict" | "failed",
  "pr_number": 42,
  "branch": "feat/foo-bar",
  "message": "詳細メッセージ"
}
```

| フィールド | 内容 |
| --- | --- |
| `verdict` | マージ結果区分 |
| `pr_number` | マージした PR 番号 |
| `branch` | ヘッドブランチ名 |
| `message` | 詳細メッセージ |
