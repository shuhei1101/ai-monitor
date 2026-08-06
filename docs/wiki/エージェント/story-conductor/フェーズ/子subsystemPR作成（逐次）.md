# 子subsystemPR作成（逐次）

subsystem-conductor のインターフェース確定報告を受けて、依存順の次の subsystem PR を 1 件作成する。

## 手順

### 次の未作成 subsystem の特定

story PR 本文の `## サブシステム一覧` から `対応 subsystem` が `未作成` の行を拾い、依存列が満たされたものを 1 件特定する。

- 未作成の行が残っていない場合、「インターフェース確定報告の Resolve」と「ラベル除去」「作業完了報告」だけを実行する（「subsystem PR の作成」と「サブシステム一覧の更新」は実行しない）
- `## サブシステム一覧` が無い場合（本文が未記入のまま配下が動き出しているとき）、インターフェース確定報告と既存の subsystem PR 本文の `### スコープ外` から次の subsystem を特定する。
  あわせて未記入のセクション（`## 概要` / `## 背景` / `## ユースケース要件` / `## サブシステム一覧`）を親 epic PR と既存の subsystem PR から補完し、MCP `update_body` で埋める（工程を巻き戻さず、以降の判断材料を揃えるため）

### インターフェース確定報告の Resolve

MCP `resolve_comments` で subsystem-conductor のインターフェース確定報告コメントを Resolve する。

### scope ラベルの用意

作成する subsystem の `scope` について MCP `create_label` を呼ぶ:
- `name`: `scope:{識別子}`
- `color`: `$AI_MONITOR_LABEL_COLOR_SCOPE` の値
- `description`: `$AI_MONITOR_LABEL_DESC_SCOPE` の値

既に存在する場合は `created: false` が返るだけで何も変わらない。

### 次の subsystem のブランチ作成

MCP `worktree_create` を呼ぶ:
- `branch`: `{type}/{scope}/{ドメイン}/{UC名}/base`（規約『ブランチ戦略』の命名形式）
- `base_ref`: `origin/{自分の story ブランチ}`

### 次の subsystem の PR 作成

MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成したブランチ
- `base_branch`: 自分の story ブランチ
- `title`: 次の subsystem 名（`{UC名} {対象システム}` 形式）
- `body`: `## 紐づく Issue`（自 PR と同じ起点の Issue 番号）のみ
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_SUBSYSTEM` の値
  - 対象システムの `scope:*` ラベル
  - 親から引き継ぐラベル（`type:*` / `リバースエンジニアリング`）

### 確認ラベルの付与

MCP `add_labels` を呼ぶ:
- `number`: 作成した PR 番号
- `is_pr`: true
- `labels`: `$AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_CONDUCTOR` の値

### サブシステム一覧の更新

story PR 本文の `## サブシステム一覧` の該当行の `対応 subsystem` 列を、作成した `#番号` に置き換える。

MCP `update_body` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `body`: 更新後本文

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `story-conductor`
- `number`: $number
