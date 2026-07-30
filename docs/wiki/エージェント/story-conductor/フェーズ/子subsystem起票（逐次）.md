# 子subsystem起票（逐次）

subsystem-conductor のインターフェース確定報告を受けて、依存順の次の subsystem を 1 件起票する。

## 手順

### 次の未起票 subsystem の特定

story Issue 本文の `## サブシステム一覧` から `対応 subsystem` が `未起票` の行を拾い、依存列が満たされたものを 1 件特定する。

- 未起票の行が残っていない場合、「インターフェース確定報告の Resolve」と「ラベル除去」「作業完了報告」だけを実行する（「subsystem Issue の起票」と「サブシステム一覧の更新」は実行しない）

### インターフェース確定報告の Resolve

MCP `resolve_comments` で subsystem-conductor のインターフェース確定報告コメントを Resolve する。

### scope ラベルの用意

起票する subsystem の `scope` について MCP `create_label` を呼ぶ:
- `name`: `scope:{識別子}`
- `color`: `$AI_MONITOR_LABEL_COLOR_SCOPE` の値
- `description`: `$AI_MONITOR_LABEL_DESC_SCOPE` の値

既に存在する場合は `created: false` が返るだけで何も変わらない。

### subsystem Issue の起票

MCP `create_child_issue` を呼ぶ:
- `parent_issue_number`: $issue_number
- `title`: 次の subsystem 名（`{UC名} {対象システム}` 形式）
- `body`: 空文字
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_SUBSYSTEM` の値
  - 対象システムの `scope:*` ラベル
  - `$AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_CONDUCTOR` の値

### サブシステム一覧の更新

story Issue 本文の `## サブシステム一覧` の該当行の `対応 subsystem` 列を、起票した `#番号` に置き換える。

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
