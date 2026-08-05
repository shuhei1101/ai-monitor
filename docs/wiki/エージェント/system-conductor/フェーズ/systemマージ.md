# systemマージ

system-architect の土台生成完了報告を受けて成果物 PR を system ブランチへマージし、子epicPR作成へ引き継ぐ。
土台生成はユーザー承認済みのため、マージ前の確認ゲートは開かない。

## 手順

### 生成物の確認

成果物ブランチの worktree（`.claude/worktrees/{ブランチ名の / を - に置換}`）へ移動し、`git pull --ff-only` でリモートの最新を取り込む。

commit された生成物（`README.md`・`docs/rules.yaml`・`docs/wiki/` 骨格・`設計図/アーキテクチャ図.md`）と `## タスク一覧` の全チェックを確認する。

### 完了報告の Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: 成果物 PR の自分宛コメントの `node_id` 配列

### Draft 解除

MCP `mark_pr_ready` を呼ぶ:
- `pr_number`: 成果物 PR の番号

Draft のままマージすると 405 で失敗する。
Ready 済みの PR に呼んでも何も起きない。

### マージ

`規約/マージ手順.md` に沿って base（system ブランチ）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、成果物 PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `unlink_stack` を呼ぶ:
- `pr_number`: 成果物 PR の番号

スタックに属したままマージすると下位の PR まで一緒にマージされるため、先に外す（外したスタックの残りはツール側で組み直される）。

続けて MCP `merge_pr` を呼ぶ:
- `pr_number`: 成果物 PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: 成果物ブランチ

### 監視面からの除去

子epicPR作成へ続くため、ここで除去するのは成果物 PR の番号だけにする（監視面の全除去は最終マージのときに行う。共通ルール『最終マージの判定』）。

MCP `remove_watch_targets` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: $number
- `watch_numbers`: 成果物 PR の番号

### 子epicPR作成への引き継ぎ

成果物 PR での用が済んだので、手番を system PR へ戻す（規約『フェーズ索引の網羅』の 1 面 1 確認ラベル）。

MCP `add_labels` を呼ぶ:
- `number`: system PR の番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_SYSTEM_CONDUCTOR` の値

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: 成果物 PR の番号
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_SYSTEM_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: $number
