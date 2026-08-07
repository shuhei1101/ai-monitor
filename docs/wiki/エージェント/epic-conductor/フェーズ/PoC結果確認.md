# PoC結果確認

epic-poc-runner の検証結果を確認し、問題なければ PoC を畳んで次の成果物 Draft PR を作成する。
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

### 成果物 Draft PR の作成

要件確定で確定した画面変更の有無に応じて、次の担当が作業する成果物ブランチ + Draft PR を 1 本作る。
手順とタスク一覧の作り方は「要件確定（完了処理）」の `### 成果物 Draft PR の作成` と同じ。

| 画面変更 | 作るブランチ | title | 次の担当 |
| --- | --- | --- | --- |
| あり | `docs/epic/{ドメイン}/mock` | `{epic のタイトル}（モック）` | mock-designer |
| なし | `docs/epic/{ドメイン}/scenario` | `{epic のタイトル}（複合ユースケースシナリオ）` | complex-scenario-writer |

続けて MCP `add_labels`（`number`: 作成した PR の番号・`is_pr`: true）で次の担当の確認ラベルを付ける。

- 画面変更ありの場合、`$AI_MONITOR_LABEL_CONFIRM_MOCK_DESIGNER` の値 + 指示コメント（`receiver`: `mock-designer`・画面方針の要点）
- 画面変更なしの場合、`$AI_MONITOR_LABEL_CONFIRM_COMPLEX_SCENARIO_WRITER` の値

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
