# 子subsystem起票（初回）

single-scenario-writer の完了報告を受けて、単一シナリオを元に subsystem 分担を洗い出し、依存順の先頭グループのみを起票する。

## 手順

### 単一シナリオの確認

epic ブランチ配下の worktree に切り替えて（story ブランチの worktree）、single-scenario-writer が commit した `docs/wiki/設計図/シナリオ/単一ユースケース/{UC名}.md` を読む。

### 実装分担の分解と依存順の決定

シナリオの結合フローから subsystem（FE / BE / 外部連携 等）を洗い出し、依存順（例: BE → FE）を決める。

### 先頭グループの起票

依存のない先頭グループの subsystem について、`create_child_issue` を呼ぶ:
- `parent_issue_number`: $issue_number
- `title`: subsystem 名
- `body`: 空文字（本文整形は subsystem-conductor が行う）
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_SUBSYSTEM` の値
  - `$AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_CONDUCTOR` の値

### 本文の更新

story Issue 本文に `## 実装分担` セクションを追記して、全 subsystem の依存順と子リンクを反映する（未起票の subsystem は `未起票` と明記）。

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: `## 実装分担` を含む更新後本文

### 完了報告の Resolve と起票結果の記録

MCP `resolve_comments` で single-scenario-writer の完了報告コメントを Resolve する。

続けて MCP `comment` を呼ぶ（待機なし）:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `story-conductor`
- `receiver`: ユーザーログイン名
- `body`: 起票結果（先頭グループの subsystem Issue リンク一覧 + 依存順の要点）

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `story-conductor`
- `number`: $issue_number
