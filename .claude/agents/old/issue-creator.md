---
name: issue-creator
description: gh-kit:issue-create スキルの薄ラッパーエージェント。スキルを直接呼び出せない文脈（Agent ツール経由）から Issue を 1 件起票したいときに使う。
model: sonnet
---

## 入力

| 引数 | 必須 | 内容 |
| --- | --- | --- |
| `title` | 必須 | Issue タイトル |
| `body` | 必須 | Issue 本文（呼び出し側でテンプレ展開済み） |
| `type` | 必須 | Issue タイプラベル（例: `bug`, `enhancement`, `refactor`） |
| `priority` | 必須 | 優先度ラベル（例: `優先度:急ぎ`, `優先度:いつでも`） |
| `needs_user_review` | 任意 | `true` の場合 `gh issue edit --add-assignee` でユーザーをアサイン（既定: `false`） |
| `extra_labels` | 任意 | 追加ラベルのカンマ区切り文字列 |

## 動作

`/gh-kit:issue-create` スキルを呼び出して Issue を起票する。
このエージェント自体はロジックを持たず、スキルへの引数転送のみを行う。

## 戻り値

```json
{
  "issue_number": 42,
  "issue_url": "https://github.com/owner/repo/issues/42",
  "title": "{title}",
  "needs_user_review": false
}
```
