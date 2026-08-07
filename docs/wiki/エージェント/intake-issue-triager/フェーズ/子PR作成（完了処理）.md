# 子PR作成（完了処理）

承認された作業単位ごとにブランチと Draft PR を作り、自分のラベルを外して役割を終える。

作業単位のレイヤー（epic / story / subsystem）は「分解判定（初回）」で判定済みのものを使う。

## 手順

### 自分宛コメントの選別

未回答・未対応の自分宛コメントが残る場合は「分解判定（応答ループ）」に戻ってユーザーに確認質問を投げる（以降の手順は実行しない）。

### ブランチの作成

承認された案の件数分、1 件ごとに MCP `worktree_create` を呼ぶ:
- `branch`: 規約『ブランチ戦略』の命名形式に沿った名前（type は intake Issue の `type:*` ラベルに対応）
- `base_ref`: `origin/master`

intake 起点の作業には親 system が無いため base は常に `master` になる。

### Draft PR の作成

作成したブランチ 1 本ごとに MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成したブランチ
- `base_branch`: `master`
- `title`: 案のタイトル
- `body`: `## 紐づく Issue`（`- #$issue_number`）のみ
- `labels`: 作業単位のレイヤーに対応する `$AI_MONITOR_LABEL_LAYER_*` の値

要件は担当の conductor が起動後に intake Issue を辿って埋める。

### 確認ラベルの付与

着手順の依存の有無で付ける範囲が変わる（規約『ブランチ戦略』の着手順の表し方）。

| 状況 | 付ける対象 |
| --- | --- |
| 分解した作業単位に着手順の依存が無い | 作成した全 PR |
| 「分解判定（初回）」の確認質問で着手順が決まっている | 着手順が先頭の 1 本だけ |

対象の PR 1 件ごとに MCP `add_labels` を呼ぶ:
- `number`: PR 番号
- `is_pr`: true
- `labels`: 作業単位のレイヤーに対応する確認ラベル（epic なら `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値）

先頭だけに付けた場合、後続は先行 PR がマージされた時点で epic-conductor が付け替える（『epicマージ』の「次の epic の起動」）。

本文の記入を終えてから付ける（先に付けると材料が揃う前に担当が動き出す）。

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
