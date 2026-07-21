# 子subsystem起票（逐次）

subsystem-conductor のインターフェース確定報告を受けて、依存順の次の subsystem を 1 件起票する。

## 手順

### 次の未起票 subsystem の特定

story Issue 本文の `## 実装分担` から、次に起票する `未起票` の subsystem を 1 件特定する。

### インターフェース確定報告の Resolve

MCP `resolve_comments` で subsystem-conductor のインターフェース確定報告コメントを Resolve する。

### subsystem Issue の起票

MCP `create_child_issue` を呼ぶ:
- `parent_issue_number`: $issue_number
- `title`: 次の subsystem 名
- `body`: 空文字
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_SUBSYSTEM` の値
  - `$AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_CONDUCTOR` の値

### 本文の更新

story Issue 本文の `## 実装分担` の該当行の `未起票` を子 subsystem リンクに置き換える。

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: 更新後本文

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
