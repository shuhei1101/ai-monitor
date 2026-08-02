# epicマージ

complex-scenario-writer の完了報告（全 pass）を受けて epic PR を master へマージする。
自 Issue が最上位かどうかで、上位への報告と後片付けの有無が変わる。

## 手順

### テスト結果とタスク一覧の確認

完了報告（全 pass）と epic PR 本文の `## 複合ユースケースシナリオテスト結果` を照合する。

続けて `## タスク一覧` が全行 `[x]` になっていることを確認する（セクションが無い epic は確認不要）。
チェックを入れるのは各行を担当した作業者なので、ここでは本文を書き換えない。

- 未チェックのまま残っている行がある場合、その担当への完了報告コメントに追記して指摘し、チェックを入れてもらってからマージする

MCP `resolve_comments` で完了報告コメントを Resolve する。

### 最終マージかの判定

初期処理で取得した epic Issue の `parent` から、最終マージか通常マージかを決める（共通ルール『最終マージの判定』）。

### Draft 解除

MCP `mark_pr_ready` を呼ぶ:
- `pr_number`: epic PR の番号

Draft のままマージすると 405 で失敗する。
Ready 済みの PR に呼んでも何も起きない。

### マージ

`規約/マージ手順.md` に沿って base（master）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、epic PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: epic PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: epic ブランチ

### epic Issue の close

MCP `close` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `reason`: `completed`

最終マージではモニターがこの close を検知して配下のセッションを一括解放するため、通常マージ / 最終マージのどちらでも実行する。

### 親 Issue への完了報告

「最終マージかの判定」で最終マージと判定した場合は本手順を実行しない（報告先の conductor が居ないため）。

通常マージの場合、親 Issue を放置すると上位レイヤーの進行が止まるので必ず報告する。

MCP `comment` を呼ぶ:
- `number`: 親 Issue 番号
- `is_pr`: false
- `sender`: `epic-conductor`
- `receiver`: 親 Issue の `layer:` に対応する conductor（`layer:system` なら `system-conductor`）
- `format`:
  - `type`: `plain`
  - `body`: epic のマージ完了報告（対象 epic Issue 番号 + マージした epic PR へのリンク + マージした内容の要約）

続けて MCP `add_labels` を呼ぶ:
- `number`: 親 Issue 番号
- `is_pr`: false
- `labels`:
  - 報告先 conductor の確認ラベルの値（`layer:system` なら `$AI_MONITOR_LABEL_CONFIRM_SYSTEM_CONDUCTOR`）

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

### 監視面の除去

判定に応じて共通ルール『最終マージの判定』の「監視面の除去」を実行する（最終マージなら全番号、通常マージならマージした PR の番号だけ）。

作業完了報告より後に置くのは、先に除去すると報告時にセッションを解決できず失敗するため（共通ルール『最終マージの判定』）。
