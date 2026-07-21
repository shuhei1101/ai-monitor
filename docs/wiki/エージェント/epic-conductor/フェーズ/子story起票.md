# 子story起票

complex-scenario-writer のシナリオ設計完了報告を受けて、ユースケース一覧の各 UC に対応する子 story Issue を起票する。
UC 一覧は要件確定で承認済みのため、ユーザー承認なしの自動完了。

## 手順

### 子 story の起票

`## ユースケース一覧` の各 UC につき 1 件、MCP `create_child_issue` を呼ぶ:
- `parent_issue_number`: $issue_number
- `title`: UC 名を反映したタイトル
- `body`: 空文字（本文整形は story-conductor が行う）
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_STORY` の値
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値

### 対応 story 列の反映

`## ユースケース一覧` の `対応 story` 列の `未起票` を起票した `#番号` に置き換える。

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: 更新した本文

### 完了報告の Resolve と起票結果の記録

MCP `resolve_comments` で complex-scenario-writer の完了報告コメントを Resolve する。

続けて MCP `comment` を呼ぶ（待機なし）:
- `number`: $issue_number
- `is_pr`: false
- `sender`: `epic-conductor`
- `receiver`: ユーザーログイン名
- `body`: 起票結果（story Issue のリンク一覧）

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `epic-conductor`
- `number`: $issue_number
