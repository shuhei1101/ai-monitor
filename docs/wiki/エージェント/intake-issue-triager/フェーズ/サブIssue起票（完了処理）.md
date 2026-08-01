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
  - `$AI_MONITOR_LABEL_LAYER_EPIC` の値
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値

### 依存の設定

「分解判定（初回）」の調査とユーザーの回答から、着手順の依存が分かっている場合だけ実行する。

- 分解した epic 同士に順序がある場合、後続の epic に先行 epic への依存を張る
- 既存の open Issue の完了を待つ必要がある場合、その Issue への依存を張る

依存 1 件ごとに MCP `set_blocked_by` を呼ぶ:
- `number`: 待つ側（後続）の epic 番号
- `blocking_numbers`: 先に終わっている必要がある Issue の番号

対象は epic 間の依存だけ。
epic 配下の story / subsystem には張らない（親の epic が着手可能になった時点で、配下は順に進む）。

親 intake Issue への依存も張らない（Sub-issue リンクが持つ）。

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
