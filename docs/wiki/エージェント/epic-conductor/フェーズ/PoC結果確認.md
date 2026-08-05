# PoC結果確認

epic-poc-runner の検証結果を確認し、問題なければ PoC を畳んで epic Draft PR を作成する。
PoC を指示した本人が結果を確認してから次へ進める（epic-poc-runner は勝手に次フェーズへ飛ばさない）。

## 手順

### 結果の照合

epic PR 本文の `## PoC 結果` と epic-poc-runner の完了報告コメントを突き合わせる。

- 実測値が成功条件を満たしているか
- 本文の結論と報告の結論が一致しているか

### 疑問ありの場合

epic PR に質問コメント（矛盾点・確認したい点）を投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（以降の手順は実行しない）。
ユーザーの回答後の再開ターンで分岐する:

- 続行指示 → 「疑問なしの場合」に合流する
- 再検証指示 → MCP `comment`（PoC PR・`is_pr`: true・`receiver`: `epic-poc-runner`・ユーザー指示の要約）を投稿し、同一 PoC PR に `$AI_MONITOR_LABEL_CONFIRM_EPIC_POC_RUNNER` の値を再付与して終了（PR・ブランチは保持したまま差し戻し）

### 疑問なしの場合

MCP `resolve_comments` で自分宛コメント（完了報告含む）を一括 Resolve する。

続けて PoC を畳む（複数の PoC PR があれば全てに実施）:

1. MCP `close` を呼ぶ（マージなし。closed PR の diff が恒久記録になる）:
   - `number`: PoC PR の番号
   - `is_pr`: true
   - `reason`: `completed`
   - `delete_branch`: true
2. MCP `worktree_remove` を呼ぶ（`branch`: PoC ブランチ）

### epic Draft PR の作成

MCP `worktree_create`（`branch`: `{type}/epic/{ドメイン}/base`・`base_ref`: `origin/{自分の epic ブランチ}`）→ MCP `create_draft_pr`（`base_branch`: 自分の epic ブランチ・`body`: `## 紐づく Issue` と `## タスク一覧`・`labels`: `$AI_MONITOR_LABEL_LAYER_EPIC` の値）→ MCP `add_watch_targets`（作成した PR の番号）の順に呼ぶ。

`## タスク一覧` の作り方は「要件確定（完了処理）」と同じ（モック作成・複合 UC シナリオ・シナリオ索引・複合 UC E2E テストの作成 / 実行を全行未チェックで列挙する）。

要件確定で確定した画面変更の有無で次の担当を割り当てる（MCP `add_labels`・`is_pr`: true）:

- 画面変更あり → `$AI_MONITOR_LABEL_CONFIRM_MOCK_DESIGNER` の値 + 指示コメント（`receiver`: `mock-designer`・画面方針の要点）
- 画面変更なし → `$AI_MONITOR_LABEL_CONFIRM_COMPLEX_SCENARIO_WRITER` の値

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
