# 子epic起票

system Issue の `## エピック一覧` から epic Issue を一括起票し、着手順の先頭だけを epic-conductor に渡す。

## 手順

### エピック一覧の読み取り

system Issue 本文の `## エピック一覧` から epic 名・所属ユースケース・着手順を読む。

### 起票する本文の組み立て

エピックのイシュー本文テンプレートを取得する（共通ルール『Wikiページのオンデマンド取得』）。

epic ごとに `## ユースケース一覧`（所属ユースケース・`対応 story` 列は全行 `未起票`）と `## 前提条件` を組み立てる。
着手順が 2 番目以降の epic は `## 前提条件` に先行 epic を `未完了` として記載する。

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
