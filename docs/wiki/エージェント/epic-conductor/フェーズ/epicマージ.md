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

初期処理で取得した epic PR の base ブランチから、最終マージか通常マージかを決める（共通ルール『最終マージの判定』）。

### 統合テストの成果物 PR のマージ

epic PR より先に、配下の統合テストの成果物 PR（`test/epic/{ドメイン}/integration`）を epic ブランチへマージする。
`規約/マージ手順.md` に沿って base（自分の epic ブランチ）を取り込み、コンフリクトがないことを確認する。

MCP `mark_pr_ready`（`pr_number`: 成果物 PR の番号）→ MCP `merge_pr`（`pr_number`: 成果物 PR の番号・`strategy`: `squash`）→ MCP `worktree_remove`（`branch`: 統合テストの成果物ブランチ）→ MCP `remove_watch_targets`（`agent_name`: `epic-conductor`・`number`: $number・`watch_numbers`: マージした成果物 PR の番号）の順に呼ぶ。

open の成果物 PR が残っていない場合は本手順を実行しない

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

### 親 PR への完了報告

「最終マージかの判定」で最終マージと判定した場合は本手順を実行しない（報告先の conductor が居ないため）。

通常マージの場合、親 PR を放置すると上位レイヤーの進行が止まるので必ず報告する。

MCP `comment` を呼ぶ:
- `number`: 親 PR 番号
- `is_pr`: true
- `sender`: `epic-conductor`
- `receiver`: 親 PR の `layer:` に対応する conductor（`layer:system` なら `system-conductor`）
- `format`:
  - `type`: `plain`
  - `body`: epic のマージ完了報告（対象 epic PR 番号 + マージした epic PR へのリンク + マージした内容の要約）

続けて MCP `add_labels` を呼ぶ:
- `number`: 親 PR 番号
- `is_pr`: true
- `labels`:
  - 報告先 conductor の確認ラベルの値（`layer:system` なら `$AI_MONITOR_LABEL_CONFIRM_SYSTEM_CONDUCTOR`）

### 次の epic の起動

「最終マージかの判定」で最終マージ（base が `master`）と判定した場合だけ実行する。
親 system がある場合は system-conductor が引き継ぐので本手順は実行しない。

起点 intake Issue から出た兄弟 epic のうち、着手を待っているものがあれば手番を渡す。

MCP `search_issues_and_prs` を呼ぶ:
- `query`: `#{起点 intake Issue の番号} is:pr is:open`

戻り値から `layer:epic` が付いた open PR を集め、確認ラベルが 1 つも付いていないものを 1 件選ぶ。

- 確認ラベル付きの epic PR が既にある場合は何もしない（その epic が進行中）
- 未着手が無い場合も何もしない（intake は配下の PR が全て merged になった時点でモニターが閉じる）

MCP `add_labels` を呼ぶ:
- `number`: 選んだ epic PR の番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値

確認ラベルが無い PR はモニターが起動しないため、この付け替えが着手順の直列化そのものになる（規約『ブランチ戦略』の着手順の表し方）。

### ラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_EPIC_CONDUCTOR` の値
- `add_labels_`: なし

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `epic-conductor`
- `number`: $number

### 監視面の除去

判定に応じて共通ルール『最終マージの判定』の「監視面の除去」を実行する（最終マージなら全番号、通常マージならマージした PR の番号だけ）。

作業完了報告より後に置くのは、先に除去すると報告時にセッションを解決できず失敗するため（共通ルール『最終マージの判定』）。
