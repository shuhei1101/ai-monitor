# サブIssue起票（完了処理）

承認されたサブ Issue 案を Sub-issue として起票し、自分のラベルを外して役割を終える。

## 手順

### 自分宛コメントの選別

未回答・未対応の自分宛コメントが残る場合は「分解判定（応答ループ）」に戻ってユーザーに確認質問を投げる（以降の手順は実行しない）。

### サブIssueの起票

承認された案を intake Issue の Sub-issue として件数分起票する。
詳細な本文は書かず、子エージェントが起動時に `parent` メタデータで親を辿って埋める。

1 件ごとに MCP `create_child_issue` を呼ぶ:
- `parent_issue_number`: $issue_number
- `title`: 案のタイトル
- `body`: 空文字
- `labels`:
  - 「分解判定（初回）」で判定した種別に応じた `layer:*` の値
  - 「分解判定（初回）」で判定した種別に応じた `確認:*` の値

### 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: 選別で Resolve 対象にしたコメントの `node_id` 配列

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_INTAKE_ISSUE_TRIAGER` の値
- `add_labels_`: なし（役割を終えるので次ラベルなし）

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `intake-issue-triager`
- `number`: $issue_number
