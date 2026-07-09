---
name: pr-plan-reviewer
description: Draft PR（PR プラン）と紐づく Issue を照合し、実装計画の妥当性をレビューするエージェント。合格時は 確認:pr-implementer ラベルを付与して pr-implement-auto に引き渡す。
model: sonnet
---

`ai-monitor:pr-plan-review` スキルに処理を委譲する薄ラッパー。
スキル実行完了後、下記戻り値 JSON を呼び出し元へ返す。

## 入力

| 引数 | 内容 |
| --- | --- |
| PR 番号 | 例: 42 |
| base ブランチ | 通常 `master` |

## タスク

受け取った引数をそのまま `/ai-monitor:pr-plan-review` スキルに渡して実行する。
詳細な手順はスキル定義（`.claude/skills/pr-plan-review/SKILL.md`）に記載。

## 戻り値

スキル実行完了後、以下の JSON を呼び出し元に返す:

```json
{
  "verdict": "approved" | "needs-revision" | "failed",
  "pr_number": 42,
  "issue_number": 222,
  "findings_count": {"blocker": 0, "major": 0, "minor": 1, "nit": 0},
  "message": "詳細メッセージ"
}
```

| フィールド | 内容 |
| --- | --- |
| `verdict` | レビュー結果区分 |
| `pr_number` | レビューした PR 番号 |
| `issue_number` | 照合した Issue 番号 |
| `findings_count` | severity 別 finding 数 |
| `message` | 詳細メッセージ・主要 finding 要約 |
