# RE完了確認

architecture-reverse-engineer が commit した現状のアーキテクチャ図を確認し、起こし漏れがないかをユーザーに確認する。

## 手順

### 起こされたページの確認

RE ブランチの worktree（`.claude/worktrees/{ブランチ名の / を - に置換}`）へ移動し、`git pull --ff-only` でリモートの最新を取り込む。

commit された `設計図/アーキテクチャ図.md` と、完了報告コメントの機能の洗い出し・読み取れなかった箇所を読む。

### 最終確認コメントの投稿

MCP `comment` を呼ぶ:
- `number`: RE PR の番号
- `is_pr`: true
- `sender`: `system-conductor`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `format`:
  - `type`: `plain`
  - `body`: 起こしたページ一覧 + 洗い出された機能の要約 + 読み取れなかった箇所 + 起こし漏れの指摘方法と承認方法の案内

### 議論中 付与 + 待機

MCP `add_labels` を呼ぶ:
- `number`: RE PR の番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_IN_DISCUSSION` の値

続けて MCP `set_assignee` を呼ぶ:
- `number`: RE PR の番号
- `is_pr`: true

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: RE PR の番号
