# 子subsystem起票（逐次）

subsystem-conductor のインターフェース確定報告を受けて、依存順の次の subsystem を 1 件起票する。

## 手順

### 次の未起票 subsystem の特定

story ブランチの単一 UC シナリオから subsystem を洗い出し、初期処理で取得した `sub_issues` と突き合わせて、依存順で次に来る未起票の subsystem を 1 件特定する。

- 未起票の subsystem が残っていない場合、「インターフェース確定報告の Resolve」と「ラベル除去」「作業完了報告」だけを実行する（「subsystem Issue の起票」は実行しない）

### インターフェース確定報告の Resolve

MCP `resolve_comments` で subsystem-conductor のインターフェース確定報告コメントを Resolve する。

### subsystem Issue の起票

MCP `create_child_issue` を呼ぶ:
- `parent_issue_number`: $issue_number
- `title`: 次の subsystem 名（`{UC名} {対象システム}` 形式）
- `body`: 空文字
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_SUBSYSTEM` の値
  - 対象システムの `scope:*` ラベル
  - `$AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_CONDUCTOR` の値

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
