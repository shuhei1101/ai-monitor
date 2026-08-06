# storyマージ

single-scenario-writer の全 pass 報告を受けて story PR を親 epic ブランチへマージし、epic-conductor に完了報告する。

## 手順

### テスト結果とタスク一覧の確認

完了報告（全 pass）と story PR 本文の `## 単一ユースケースシナリオテスト結果` を照合する。

続けて `## タスク一覧` が全行 `[x]` になっていることを確認する（セクションが無い story は確認不要）。
チェックを入れるのは各行を担当した作業者なので、ここでは本文を書き換えない。

- 未チェックのまま残っている行がある場合、その担当への完了報告コメントに追記して指摘し、チェックを入れてもらってからマージする

MCP `resolve_comments` で完了報告コメントを Resolve する。

### Draft 解除

MCP `mark_pr_ready` を呼ぶ:
- `pr_number`: story PR の番号（初期処理の監視面から取得）

Draft のままマージすると 405 で失敗する。
Ready 済みの PR に呼んでも何も起きない。

### マージ

`規約/マージ手順.md` に沿って base（親 epic ブランチ）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、story PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: story PR の番号（初期処理の監視面から取得）
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: story ブランチ

### 親 epic PR への完了報告

MCP `comment` を呼ぶ:
- `number`: 親 epic PR 番号
- `is_pr`: true
- `sender`: `story-conductor`
- `receiver`: `epic-conductor`
- `format`:
  - `type`: `plain`
  - `body`: story のマージ完了報告（対象 story PR 番号 + マージした story PR へのリンク + マージ済み subsystem のサマリ）

続けて MCP `add_labels` を呼ぶ:
- `number`: 親 epic PR 番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `story-conductor`
- `number`: $number
