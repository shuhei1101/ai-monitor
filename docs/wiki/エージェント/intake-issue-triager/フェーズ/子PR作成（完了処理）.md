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

詳細な本文は書かない。
要件は担当の conductor が起動後に intake Issue を辿って埋める。

### スタックへの接続

「分解判定（初回）」の調査とユーザーの回答から、着手順の依存が分かっている場合だけ実行する。

分解した作業単位同士に順序がある場合、後続の PR を先行 PR の上に積む。
スタックの並びがそのまま着手順になり、モニターは下に open な PR が残っている間その PR を起動しない。

MCP `link_stack` を呼ぶ:
- `pull_requests`: 着手順に並べた PR 番号の配列（下から上）

順序が無い場合は呼ばない（並列に進む）。

### 確認ラベルの付与

作成した PR 1 件ごとに MCP `add_labels` を呼ぶ:
- `number`: PR 番号
- `is_pr`: true
- `labels`: 作業単位のレイヤーに対応する確認ラベル（epic なら `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値）

スタックに積んだ PR にも同じく付ける。
先行 PR が open のうちはモニターが起動を見送るため、依存の解消を待つ制御は自分では行わない。

本文とスタックの接続を終えてから付ける（先に付けると材料が揃う前に担当が動き出す）。

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
