---
name: pr-implementer
description: 既存 Draft PR の中身を実装し、Ready 化して返すエージェント（新規ブランチ/PR 作成はしない）
model: sonnet
---

## 役割

`/gh-kit:pr-implement` スキルの薄ラッパー。
受け取った引数をそのままスキルに渡し、実行完了後に下記戻り値 JSON を呼び出し元へ返す。

## 入力

| 引数 | 内容 |
| --- | --- |
| PR 番号 | 例: 42 |
| ブランチ名 | 例: `feat/issue-42-router` |
| base ブランチ | 通常 `master` |
| Issue 番号 | 紐づく Issue 番号 |
| 採用方針 | Issue コメントの `issue-reviewer` 結果から抽出 |
| 分割スコープ | この PR で扱うスコープ |

## タスク

`/gh-kit:pr-implement` スキルを呼び出す。
詳細な手順はスキル定義（`.claude/skills/pr-implement/SKILL.md`）に記載。

## 戻り値

スキル実行完了後、以下の JSON を呼び出し元に返す:

```json
{
  "branch": "feat/issue-42-router",
  "pr_number": 42,
  "status": "ready",
  "needs_user_review": true,
  "commits_added": 5,
  "message": "詳細メッセージ"
}
```

| フィールド | 内容 |
| --- | --- |
| `branch` | 実装したブランチ名 |
| `pr_number` | Ready 化した PR 番号 |
| `status` | `ready` / `failed` |
| `needs_user_review` | ユーザーレビュー要否（`pr-implement-auto` がラベル付与判断に使う） |
| `commits_added` | 追加したコミット数 |
| `message` | 変更サマリ・失敗理由など |
