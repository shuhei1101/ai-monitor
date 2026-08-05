# epicPR作成

面が Issue のまま手番が渡ってきたとき、epic ブランチ + Draft PR を作って確認ラベルを PR へ移す。

通常の epic は intake-issue-triager が PR まで作るのでこのフェーズは通らない。
ユーザーが Issue へ直接 `確認:epic-conductor` を付けた場合だけ、ここが入口になる（system-conductor の立ち上げ Issue と同じ位置づけ）。

PR を作った時点で以降のやり取りは PR 上に移り、次のターンから「要件確定（初回）」が通常どおり動く。

## 手順

### ラベルの付与

Issue に `layer:*` / `type:*` が付いていない場合だけ実行する。

MCP `add_labels` を呼ぶ:
- `number`: $number
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_EPIC` の値
  - Issue の本文から判定した `type:*` ラベルの値（判定基準は intake-issue-triager『分解判定（初回）』の `### type / layer ラベルの付与` と同じ）

### base の決定

親 system PR があればそのブランチ、無ければ `master` を base にする（規約『ブランチ戦略』）。

初期処理で取得した `parent` が `layer:system` の PR なら、その `head_ref` が base になる。
`parent` が無い、または親が intake Issue の場合は `master`。

### epic ブランチの作成

Issue のタイトルと本文から決めたドメイン名で epic ブランチを組み立てる。

MCP `worktree_create` を呼ぶ:
- `branch`: `{type}/epic/{ドメイン}/base`（type は前手順で付けた `type:*` に対応）
- `base_ref`: `origin/{決定した base}`

### epic Draft PR の作成

MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成した epic ブランチ
- `base_branch`: 決定した base
- `title`: Issue のタイトル
- `body`: `## 紐づく Issue`（`- #$number`）のみ
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_EPIC` の値
  - Issue に付いているのと同じ `type:*` ラベルの値
  - `リバースエンジニアリング` ラベルがある場合はその値

要件は次のターンの「要件確定（初回）」が書くので、ここでは本文を作り込まない。

### 監視面の登録

MCP `add_watch_targets` を呼ぶ:
- `agent_name`: `epic-conductor`
- `number`: $number
- `watch_numbers`: 作成した PR の番号

### 確認ラベルの付け替え

以降のやり取りは epic PR 上で行うため、手番を Issue から PR へ移す。

MCP `add_labels` を呼ぶ:
- `number`: 作成した PR の番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値

続けて MCP `transition_phase` を呼ぶ:
- `number`: $number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値
- `add_labels_`: なし

起点の Issue は close せず open のまま残す（`## 紐づく Issue` の参照先で、配下の PR が全てマージされた時点でモニターが閉じる）。

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `epic-conductor`
- `number`: $number
