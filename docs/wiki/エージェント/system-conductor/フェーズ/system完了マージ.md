# system完了マージ

配下の全 epic PR がマージされたことを確認して system PR を master へマージし、起点の立ち上げ Issue を閉じる。

## 手順

### エピック一覧の確認

system PR 本文の `## エピック一覧` の `対応 PR` 列の番号を 1 件ずつ MCP `get_issue_or_pr` で取得し、全て merged かを確認する。

- open の epic PR が残っている場合、報告コメントを Resolve して「ラベル除去」「作業完了報告」だけを実行する（残りの epic の完了報告で再び起動される）

### 完了報告の Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: system PR の自分宛コメントの `node_id` 配列

### Draft 解除

MCP `mark_pr_ready` を呼ぶ:
- `pr_number`: system PR の番号

Draft のままマージすると 405 で失敗する。
Ready 済みの PR に呼んでも何も起きない。

### マージ

system ブランチの worktree へ移動し、`規約/マージ手順.md` に沿って base（`master`）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、system PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `unlink_stack` を呼ぶ:
- `pr_number`: system PR の番号

続けて MCP `merge_pr` を呼ぶ:
- `pr_number`: system PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: system ブランチ

### 起点 Issue のクローズ

base が `master` の最終マージなので、起点の立ち上げ Issue をここで閉じる（規約『マージ手順』）。

MCP `close` を呼ぶ:
- `number`: $number
- `is_pr`: false
- `reason`: `completed`

### 完了報告

MCP `comment` を呼ぶ:
- `number`: $number
- `is_pr`: false
- `sender`: `system-conductor`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `format`:
  - `type`: `plain`
  - `body`: system の完了報告（マージした system PR へのリンク + 配下 epic の一覧）

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: system PR の番号
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_SYSTEM_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: $number

### 監視面の除去

最終マージなので監視面に残っている全番号を除去する（共通ルール『最終マージの判定』）。

MCP `remove_watch_targets` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: $number
- `watch_numbers`: 監視面に残っている全番号
