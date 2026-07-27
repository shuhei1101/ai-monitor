# ライブラリPoC発注

合意された候補と検証観点をもとに候補ごとの PoC PR を作成し、library-poc-runner へ検証を発注する。

## 手順

### PoC ブランチと PoC PR の作成

subsystem ブランチ名 `{type}/{scope}/{ドメイン}/{UC名}/{変更内容}` から scope・ドメイン・UC 名を取り出す。

候補ごとに MCP `worktree_create` を呼ぶ:
- `branch`: `poc/{scope}/{ドメイン}/{UC名}/{lib名}`
- `base_ref`: `origin/master`

続けて候補ごとに MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成したブランチ
- `base_branch`: `master`
- `title`: `PoC: {ライブラリ名}（#{親 subsystem Issue 番号}）`
- `body`: テンプレート「PR本文/ライブラリPoC」の `## 紐づく Issue` / `## 発注元 PR` / `## 検証対象` / `## 調査結果` / `## 検証観点と結果`（観点と成功条件まで。実測値・判定は `-`）

### 候補比較コメントへの PoC PR 一覧の追記

MCP `reply_comment` を呼ぶ:
- `comment_node_id`: 候補比較コメントの node_id
- `sender`: `architect`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `body`: 作成した PoC PR のリンク一覧（候補ごと 1 行）

### 監視面の登録

MCP `add_watch_targets` を呼ぶ:
- `agent_name`: `architect`
- `number`: $pr_number
- `watch_numbers`: 作成した全 PoC PR の番号

### library-poc-runner への検証発注

PoC PR ごとに MCP `comment` を呼ぶ:
- `number`: PoC PR の番号
- `is_pr`: true
- `sender`: `architect`
- `receiver`: `library-poc-runner`
- `body`: 検証指示（本文の `## 検証観点と結果` に沿って検証し、実測値・判定・所感を本文へ記録する旨）

続けて PoC PR ごとに MCP `add_labels` を呼ぶ:
- `number`: PoC PR の番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_LIBRARY_POC_RUNNER` の値

### 待機

MCP `set_assignee` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true

subsystem PR の `確認:architect` と `議論中` は保持したまま検証結果を待つ（結果は PoC PR 側の完了報告で戻る）。

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `architect`
- `number`: $pr_number
