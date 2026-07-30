# epicマージ

complex-scenario-writer の完了報告（全 pass）を受けて epic PR を master へマージする。
自 Issue が最上位かどうかで、上位への報告と後片付けの有無が変わる。

## 手順

### テスト結果の確認

完了報告（全 pass）と epic PR 本文の `## 複合ユースケースシナリオテスト結果` を照合する。

MCP `resolve_comments` で完了報告コメントを Resolve する。

### 最終マージかの判定

初期処理で取得した epic Issue の `parent` を見て、どちらの経路かを決める（共通ルール『最終マージの判定』）。

| 親 Issue | 判定 | この後やること |
| --- | --- | --- |
| なし、または `layer:intake` | 最終マージ | マージ後に監視面を全て除去する（上位報告なし） |
| `layer:system` の system Issue | 通常マージ | マージ後に epic PR の番号だけを監視面から除去し、親へ完了報告する |
| 上記以外 | 通常マージ | 同上（報告先は親 Issue の `layer:` に対応する conductor） |

### マージ

`規約/マージ手順.md` に沿って base（master）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、epic PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: epic PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: epic ブランチ

### 監視面の除去

MCP `remove_watch_targets` を呼ぶ:
- `agent_name`: `epic-conductor`
- `number`: $issue_number
- `watch_numbers`: 最終マージの場合は監視面に残っている全番号、通常マージの場合は epic PR の番号のみ

### 親への完了報告

最終マージの場合は本手順を実行しない。

MCP `comment` を呼ぶ:
- `number`: 親 Issue 番号
- `is_pr`: false
- `sender`: `epic-conductor`
- `receiver`: 親 Issue の `layer:` に対応する conductor（`layer:system` なら `system-conductor`）
- `format`:
  - `type`: `plain`
  - `body`: epic のマージ完了報告（対象 epic Issue 番号 + 実装内容の要約）

続けて MCP `add_labels` を呼ぶ:
- `number`: 親 Issue 番号
- `is_pr`: false
- `labels`:
  - 報告先 conductor の確認ラベルの値

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `epic-conductor`
- `number`: $issue_number
