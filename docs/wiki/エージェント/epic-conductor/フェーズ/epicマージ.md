# epicマージ

complex-scenario-writer の完了報告（全 pass）を受けて epic PR を master へマージする終端処理。
最上位のため上位への完了報告はない（epic Issue はマージで自動 close、セッション解放はモニターの直轄）。

## 手順

### テスト結果の確認

完了報告（全 pass）と epic PR 本文の `## 複合ユースケースシナリオテスト結果` を照合する。

MCP `resolve_comments` で完了報告コメントを Resolve する。

### マージ

`規約/マージ手順.md` に沿って base（master）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、epic PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: epic PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: epic ブランチ

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値
- `add_labels_`: なし（最上位のため上位報告なし）

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `epic-conductor`
- `number`: $issue_number
