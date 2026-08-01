# 子epic起票

system Issue の `## エピック一覧` から epic Issue を一括起票し、着手順の先頭だけを epic-conductor に渡す。

## 手順

### エピック一覧の読み取り

system Issue 本文の `## エピック一覧` から epic 名・所属ユースケース・着手順を読む。

### 起票する本文の組み立て

エピックのイシュー本文テンプレートを取得する（共通ルール『Wikiページのオンデマンド取得』）。

epic ごとに `## ユースケース一覧`（所属ユースケース・`対応 story` 列は全行 `未起票`）を組み立てる。

着手順が 2 番目以降の epic は、起票後に MCP `set_blocked_by` を呼んで先行 epic への依存を設定する:
- `number`: 起票した epic の番号
- `blocking_numbers`: 直前の epic の番号

依存先の状態は `get_issue_or_pr` の `blocked_by[].state` で取れるため、本文には書かない。

### 子 Issue の起票

epic 1 件ごとに MCP `create_child_issue` を呼ぶ:
- `parent_issue_number`: $issue_number
- `title`: epic 名
- `body`: 組み立てた本文
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_EPIC` の値
  - 新規プロジェクトの場合は `$AI_MONITOR_LABEL_TYPE_FEAT` の値、既存プロジェクトの移行の場合は `$AI_MONITOR_LABEL_TYPE_DOCS` の値
  - system Issue に `リバースエンジニアリング` が付いている場合は `$AI_MONITOR_LABEL_REVERSE_ENGINEERING` の値

### 先頭 epic の起動

MCP `add_labels` を呼ぶ:
- `number`: 着手順が先頭の epic Issue 番号
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値

### エピック一覧への反映

`## エピック一覧` の `対応 Issue` 列を起票した番号（`#N`）で全行更新する。

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: 更新後本文

### 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: system Issue の自分宛コメントの `node_id` 配列

### 監視面の整理

system Issue は最上位（親 Issue を持たない）なので、後片付けは本エージェントが担う（共通ルール『最終マージの判定』）。
起票した epic の進行中は epic 側の conductor が自分の監視面を持つため、ここでは自分の監視面に PR 番号が残っていないことだけを確認する。

- 残っている番号がある場合、MCP `remove_watch_targets` で除去する（`agent_name`: `system-conductor`・`number`: $issue_number）

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_SYSTEM_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: $issue_number
