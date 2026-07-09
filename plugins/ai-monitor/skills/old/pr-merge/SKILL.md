---
name: ai-monitor:pr-merge
description: 確認:pr-merger ラベル付き PR を 1 件 base へマージし、worktree 削除・push まで実行する
---

# pr-merge

`確認:pr-merger` ラベルが付いた PR を base ブランチへマージする。
レビュー責務は持たない（`pr-review` が承認済み前提）。

## 入力

| 引数 | 内容 |
| --- | --- |
| PR 番号 | 例: 42 |
| ベースブランチ | 例: `master` |
| ヘッドブランチ | 例: `feat/foo-bar` |
| リポジトリ root | メインリポジトリの絶対パス |

## ステップ 1: PR 情報確認

```bash
gh pr view {N} --json number,title,body,headRefName,baseRefName,labels,assignees,isDraft,statusCheckRollup
```

- `isDraft: true` なら `failed` で返して停止
- `確認:pr-merger` ラベルが付いていなければ `failed` で返して停止
- assignees が設定されていれば `failed` で返して停止（ユーザー確認待ちのため）
- CI が failure なら `failed` で返して停止

## ステップ 2: ワークツリーを最新化

```bash
WT=".claude/worktrees/$(echo {HEAD_BRANCH} | tr '/' '-')"
git -C "$WT" fetch origin
git -C "$WT" reset --hard origin/{HEAD_BRANCH}
```

## ステップ 3: ベースブランチを取り込む

```bash
git -C "$WT" merge origin/{BASE_BRANCH}
```

コンフリクトが残ったら `git -C "$WT" status -s` で UU / AA / DD などのコードを確認し、両側の意図を読んで「意味が強い」方を採用または両立させる（`-X ours` / `-X theirs` 一括解消は禁止）。解消後 `git -C "$WT" add` / `git -C "$WT" commit`。

自走解消できなかった場合は、以下を実行してユーザーに通知する:

```bash
# コンフリクトファイル一覧を取得
CONFLICT_FILES=$(git -C "$WT" status -s | grep '^UU\|^AA\|^DD' | awk '{print "- `" $2 "`"}')
```

`ai-monitor-tools` MCP の `template_get` で `コンフリクト通知コメント.j2` を取得し、以下の変数を埋めて `gh pr comment` で投稿する:

| 変数 | 内容 |
| --- | --- |
| `{head_branch}` | HEAD ブランチ名 |
| `{base_branch}` | BASE ブランチ名 |
| `{conflict_files}` | `$CONFLICT_FILES` の値 |
| `{conflict_reason}` | AI が判断した解消不能の理由 |

```bash
# テンプレートに変数を埋めたコメントを投稿
gh pr comment {PR_NUMBER} --body "{テンプレートに変数を埋めた本文}"

# assignee にユーザーを追加して通知
gh pr edit {PR_NUMBER} --add-assignee @me
```

自走解消できなかった場合は verdict = `conflict` で返して停止。

## ステップ 4: --no-ff でマージ

```bash
git -C {REPO_ROOT} merge --no-ff -m "{type}: {title}" {HEAD_BRANCH}
```

## ステップ 5: worktree 削除 + push

`ai-monitor-tools` MCP の `worktree_remove`（`branch={HEAD_BRANCH}`）を呼んでワークツリーとブランチを削除。リモートブランチを削除してから base ブランチを push する。

```bash
git push origin --delete {HEAD_BRANCH}
git -C {REPO_ROOT} push origin {BASE_BRANCH}
```

## ステップ 6: Issue close + ラベル整理

```bash
. "${CLAUDE_PLUGIN_ROOT}/scripts/constants.sh"
# PR 本文から "Refs #N" または "Closes #N" で Issue 番号を抽出
ISSUE_N=$(gh pr view {PR_NUMBER} --json body --jq '.body' | grep -oP '(?:Refs|Closes|Fixes) #\K[0-9]+' | head -1)
if [ -n "$ISSUE_N" ]; then
  gh issue close "$ISSUE_N"
  gh issue edit "$ISSUE_N" \
    --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_ARCH" \
    --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_IMPL" \
    --remove-label "$AI_MONITOR_LABEL_PROCESSING_PR_IMPL_REVIEW"
fi
```

## 戻り値

| 状況 | verdict |
| --- | --- |
| 全て成功 | `merged` |
| コンフリクトが自走解消できず残る（コメント通知 + assignee 追加済み） | `conflict` |
| その他失敗 | `failed` |

## 制約

| No | 禁止 |
| --- | --- |
| 1 | レビューはしない（`pr-review` の責務） |
| 2 | `git push --force` は使わない |
| 3 | assignees が設定されている PR をマージしない |
| 4 | Draft PR をマージしない |
