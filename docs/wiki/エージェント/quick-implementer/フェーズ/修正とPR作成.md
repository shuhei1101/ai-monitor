# 修正とPR作成

chore Issue の指示どおりに修正して PR を作り、内容の確認を依頼して待機に入る。

## 手順

### worktree の作成

MCP `worktree_create` を呼ぶ:
- `branch`: `chore/{分類}/{変更内容}`（分類は Issue のラベル・内容から決める）
- `base_ref`: `origin/master`

### 修正の commit push

作成した worktree で chore Issue の指示どおりに修正し、commit push する。
テストコード・Wiki の更新は行わない（軽微修正の範囲に閉じる）。

### PR の作成

MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成したブランチ
- `base_branch`: `master`
- `title`: chore Issue のタイトル
- `body`: テンプレート「PR本文/軽微修正」の `## 紐づく Issue` / `## 概要`

続けて MCP `mark_pr_ready` を呼ぶ:
- `pr_number`: 作成した PR 番号

レビュー工程は挟まないので、作成後すぐ Ready 化する（`確認:*` ラベルは付けない）。

### 監視面の登録

MCP `add_watch_targets` を呼ぶ:
- `agent_name`: `quick-implementer`
- `number`: $issue_number
- `watch_numbers`: 作成した PR 番号

### インラインコメントの投稿

commit した内容を読み返し、共通ルール『インラインコメント』に沿って確認事項と補足事項を該当行へ投稿する。

### 確認依頼 + 待機

MCP `comment` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `quick-implementer`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `format`:
  - `type`: `commits`
  - `body`: 確認依頼（PR リンク + 変更内容の要約）
  - `entries`: 積んだ commit の `commit` と `summary` の組

続けて MCP `add_labels` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_IN_DISCUSSION` の値

続けて MCP `set_assignee` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `quick-implementer`
- `number`: $issue_number
