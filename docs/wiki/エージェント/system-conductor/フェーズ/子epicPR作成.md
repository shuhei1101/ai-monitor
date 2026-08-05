# 子epicPR作成

system PR の `## エピック一覧` から epic PR を一括作成し、着手順の先頭だけを epic-conductor に渡す。

## 手順

### エピック一覧の読み取り

system PR 本文の `## エピック一覧` から epic 名・所属ユースケース・着手順を読む。

### 作成する本文の組み立て

エピックの PR 本文テンプレートを取得する（共通ルール『Wikiページのオンデマンド取得』）。

epic ごとに `## 紐づく Issue`（自 PR と同じ起点の Issue 番号）と `## ユースケース一覧`（所属ユースケース・`対応 story` 列は全行 `未作成`）を組み立てる。

### 子 epic ブランチの作成

epic 1 件ごとに MCP `worktree_create` を呼ぶ:
- `branch`: `{type}/epic/{ドメイン}/base`（規約『ブランチ戦略』の命名形式）
- `base_ref`: `origin/{自分の system ブランチ}`

### 子 epic PR の作成

作成したブランチ 1 本ごとに MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成したブランチ
- `base_branch`: 自分の system ブランチ
- `title`: epic 名
- `body`: 組み立てた本文
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_EPIC` の値
  - 新規プロジェクトの場合は `$AI_MONITOR_LABEL_TYPE_FEAT` の値、既存プロジェクトの移行の場合は `$AI_MONITOR_LABEL_TYPE_DOCS` の値
  - system PR に `リバースエンジニアリング` が付いている場合は `$AI_MONITOR_LABEL_REVERSE_ENGINEERING` の値

### スタックへの接続

着手順が 2 番目以降の epic PR を、先行 epic PR の上に積む。

MCP `link_stack` を呼ぶ:
- `pull_requests`: 着手順に並べた epic PR 番号の配列（下から上）

スタックの並びが着手順になり、モニターは下に open な PR が残っている間その PR を起動しない。

### 先頭 epic の起動

MCP `add_labels` を呼ぶ:
- `number`: 着手順が先頭の epic PR 番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値

### エピック一覧への反映

`## エピック一覧` の `対応 PR` 列を作成した番号（`#N`）で全行更新する。

MCP `update_body` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `body`: 更新後本文

### 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: system PR の自分宛コメントの `node_id` 配列

### 監視面の整理

system PR は最上位（base が `master` で親レイヤーの PR を持たない）なので、後片付けは本エージェントが担う（共通ルール『最終マージの判定』）。
作成した epic の進行中は epic 側の conductor が自分の監視面を持つため、ここでは自分の監視面に PR 番号が残っていないことだけを確認する。

- 残っている番号がある場合、MCP `remove_watch_targets` で除去する（`agent_name`: `system-conductor`・`number`: $number）

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_SYSTEM_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: $number
