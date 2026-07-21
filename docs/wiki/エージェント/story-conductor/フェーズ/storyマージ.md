# storyマージ

single-scenario-writer の全 pass 報告を受けて story PR を親 epic ブランチへマージし、epic-conductor に完了報告する。

## 手順

### テスト結果の確認

完了報告（全 pass）と story PR 本文の `## 単一ユースケースシナリオテスト結果` を照合する。

MCP `resolve_comments` で完了報告コメントを Resolve する。

### マージ

`規約/マージ手順.md` に沿って base（親 epic ブランチ）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、story PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: story PR の番号（初期処理の監視面から取得）
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: story ブランチ

### 親 epic Issue への完了報告

MCP `add_labels` を呼ぶ:
- `number`: 親 epic Issue 番号
- `is_pr`: false
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値

続けて MCP `comment` を呼ぶ:
- `number`: 親 epic Issue 番号
- `is_pr`: false
- `sender`: `story-conductor`
- `receiver`: `epic-conductor`
- `body`: story のマージ完了報告（対象 story Issue 番号 + 実装分担のサマリ）

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値
- `add_labels_`: なし（story Issue は PR マージで自動 close）

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `story-conductor`
- `number`: $issue_number
