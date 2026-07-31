# subsystemマージ

ユーザーの最終承認を受けて subsystem PR を親 story ブランチへマージし、story-conductor に完了報告する。

## 手順

### 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: subsystem PR の自分宛コメントの `node_id` 配列

### Draft 解除

MCP `mark_pr_ready` を呼ぶ:
- `pr_number`: subsystem PR の番号

Draft のままマージすると 405 で失敗する。
Ready 済みの PR に呼んでも何も起きない。

### マージ

`規約/マージ手順.md` に沿って base（親 story ブランチ）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、subsystem PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: subsystem PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: subsystem ブランチ

### subsystem Issue の close

MCP `close` を呼ぶ:
- `number`: 対象 subsystem Issue 番号（subsystem PR 本文の `## 紐づく Issue`）
- `is_pr`: false
- `reason`: `completed`

完了報告より前に閉じる。
story-conductor は全子 subsystem が closed かどうかで統合テストの委任と状況確認を分けるため、open のまま報告すると委任側の分岐に入れない。

### 親 story Issue への完了報告

MCP `comment` を呼ぶ:
- `number`: 親 story Issue 番号
- `is_pr`: false
- `sender`: `subsystem-conductor`
- `receiver`: `story-conductor`
- `format`:
  - `type`: `plain`
  - `body`: 完了報告（対象 subsystem Issue 番号 + 実装内容の要約）。バグ差し戻し由来の修正用 PR の場合は、修正完了報告であることと修正内容を書く

続けて MCP `add_labels` を呼ぶ:
- `number`: 親 story Issue 番号
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: subsystem PR の番号
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_SUBSYSTEM_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `subsystem-conductor`
- `number`: subsystem PR の番号
