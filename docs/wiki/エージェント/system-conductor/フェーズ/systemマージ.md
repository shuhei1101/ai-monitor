# systemマージ

system-architect の土台生成完了報告を受けて system PR を master へマージし、子epic起票へ引き継ぐ。
土台生成はユーザー承認済みのため、マージ前の確認ゲートは開かない。

## 手順

### 生成物の確認

system ブランチの worktree（`.claude/worktrees/{ブランチ名の / を - に置換}`）へ移動し、`git pull --ff-only` でリモートの最新を取り込む。

commit された生成物（`README.md`・`docs/rules.yaml`・`docs/wiki/` 骨格・`設計図/アーキテクチャ図.md`）と `## タスク一覧` の全チェックを確認する。

### 完了報告の Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: system PR の自分宛コメントの `node_id` 配列

### マージ

`規約/マージ手順.md` に沿って base（`master`）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、system PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: system PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: system ブランチ

### 監視面からの除去

MCP `remove_watch_targets` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: $issue_number
- `watch_numbers`: system PR の番号

### 子epic起票への引き継ぎ

MCP `add_labels` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_SYSTEM_CONDUCTOR` の値

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
- `number`: system PR の番号
