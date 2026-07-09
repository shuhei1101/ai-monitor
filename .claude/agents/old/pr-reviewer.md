---
name: pr-reviewer
description: 1 PR をレビューし、合格 + assignees なしなら 確認:pr-merger ラベルを付与して pr-merger に委譲する
model: sonnet
---

`gh-kit:pr-review` スキルに処理を委譲する薄ラッパー。
スキル実行完了後、下記戻り値 JSON を呼び出し元へ返す。

## 入力

| 引数 | 内容 |
| --- | --- |
| PR 番号 | 例: 42 |
| ベースブランチ | 例: `master` |
| ヘッドブランチ | 例: `feat/foo-bar` |
| リポジトリ root | メインリポジトリの絶対パス |
| 現在 assignees 一覧 | assignees の有無を判定するのに使う |

## タスク

受け取った引数をそのまま `/gh-kit:pr-review` スキルに渡して実行する。

## 戻り値

スキル実行完了後、以下の JSON を呼び出し元に返す:

```json
{
  "verdict": "approved-merge-ok" | "approved-user-review-pending" | "changes-requested" | "needs-fix" | "failed",
  "pr_number": 42,
  "branch": "feat/foo-bar",
  "message": "詳細メッセージ",
  "findings_count": {"blocker": 0, "critical": 0, "major": 1, "minor": 2, "nit": 3}
}
```

| フィールド | 内容 |
| --- | --- |
| `verdict` | レビュー結果区分 |
| `pr_number` | レビューした PR 番号 |
| `branch` | ヘッドブランチ名 |
| `message` | 詳細メッセージ・主要 finding 要約 |
| `findings_count` | severity 別 finding 数 |
