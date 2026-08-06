# storyPR作成

面が Issue のまま手番が渡ってきたとき、story ブランチ + Draft PR を作って確認ラベルを PR へ移す。

通常の story は epic-conductor が『子storyPR作成』で PR まで作るのでこのフェーズは通らない。
ユーザーが Issue へ直接 `確認:story-conductor` を付けた場合だけ、ここが入口になる（epic-conductor『epicPR作成』と同じ位置づけ）。

PR を作った時点で以降のやり取りは PR 上に移り、次のターンから「要件確定（初回）」が通常どおり動く。

## 手順

### ラベルの付与

Issue に `layer:*` / `type:*` が付いていない場合だけ実行する。

MCP `add_labels` を呼ぶ:
- `number`: $number
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_STORY` の値
  - Issue の本文から判定した `type:*` ラベルの値（判定基準は intake-issue-triager『分解判定（初回）』の `### type / layer ラベルの付与` と同じ）

### base の決定

親 epic PR の head ブランチを base にする（規約『ブランチ戦略』）。

初期処理で取得した `parent` が `layer:epic` の PR なら、その `head_ref` が base になる。
`parent` が epic Issue で epic PR が未作成の場合は、この面をまだ進められないため「差し戻し」へ進む。

### 差し戻し

親 epic PR が無い場合だけ実行する（以降の手順は実行しない）。

story ブランチは epic ブランチから生やすため、親が PR になっていないと作れない。

MCP `comment` を呼ぶ:
- `number`: $number
- `is_pr`: false
- `sender`: `story-conductor`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `format`:
  - `type`: `plain`
  - `body`: 親 epic が PR になっていないため着手できない旨と、先に epic 側を起動してほしい依頼

続けて MCP `transition_phase` を呼ぶ:
- `number`: $number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値
- `add_labels_`: なし

「作業完了報告」を実行して自ターンを終える。

### story ブランチの作成

Issue のタイトルと本文から決めたドメイン名と UC 名で story ブランチを組み立てる。

MCP `worktree_create` を呼ぶ:
- `branch`: `{type}/story/{ドメイン}/{UC名}/base`（type は前手順で付けた `type:*` に対応）
- `base_ref`: `origin/{決定した base}`

### story Draft PR の作成

MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成した story ブランチ
- `base_branch`: 決定した base
- `title`: Issue のタイトル
- `body`: `## 紐づく Issue`（起点の Issue 番号を 1 件）のみ
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_STORY` の値
  - Issue に付いているのと同じ `type:*` ラベルの値
  - `リバースエンジニアリング` ラベルがある場合はその値

`## 紐づく Issue` に書くのは起点の Issue（intake Issue、system レイヤーから始まる場合は立ち上げ Issue）で、起動要因になった自 Issue とは限らない（規約『ブランチ戦略』の「親子関係の表し方」）。
親 epic PR の `## 紐づく Issue` と同じ番号を書く。

要件は次のターンの「要件確定（初回）」が書くので、ここでは本文を作り込まない。

### 監視面の登録

MCP `add_watch_targets` を呼ぶ:
- `agent_name`: `story-conductor`
- `number`: $number
- `watch_numbers`: 作成した PR の番号

### 確認ラベルの付け替え

以降のやり取りは story PR 上で行うため、手番を Issue から PR へ移す。

MCP `add_labels` を呼ぶ:
- `number`: 作成した PR の番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値

続けて MCP `transition_phase` を呼ぶ:
- `number`: $number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値
- `add_labels_`: なし

起動要因になった Issue も起点の Issue も close せず open のまま残す。

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `story-conductor`
- `number`: $number
