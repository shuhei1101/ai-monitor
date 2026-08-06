# 子storyPR作成

complex-scenario-writer のシナリオ設計完了報告を受けて、ユースケース一覧の各 UC に対応する子 story PR を作成する。
UC 一覧は要件確定で承認済みのため、ユーザー承認なしの自動完了。

複合ユースケースへの影響なしと確定した epic では、シナリオ設計を挟まずに要件確定の次のターンで本フェーズへ入る。
この場合は完了報告コメントが無いため「完了報告の Resolve と作成結果の記録」の Resolve は行わない。

## 手順

### 子 story ブランチの作成

`## ユースケース一覧` の各 UC につき 1 件、MCP `worktree_create` を呼ぶ:
- `branch`: `{type}/story/{ドメイン}/{UC名}/base`（規約『ブランチ戦略』の命名形式）
- `base_ref`: `origin/{自分の epic ブランチ}`

### 子 story PR の作成

作成したブランチ 1 本ごとに MCP `create_draft_pr` を呼ぶ:
- `head_branch`: 作成したブランチ
- `base_branch`: 自分の epic ブランチ
- `title`: UC 名を反映したタイトル
- `body`: `## 紐づく Issue`（自 PR の `## 紐づく Issue` と同じ起点の Issue 番号）のみ
- `labels`:
  - `$AI_MONITOR_LABEL_LAYER_STORY` の値
  - 親から引き継ぐラベル（`type:*` / `リバースエンジニアリング`）

本文の要件は story-conductor が起動後に埋める。

### 確認ラベルの付与

作成した PR 1 件ごとに MCP `add_labels` を呼ぶ:
- `number`: PR 番号
- `is_pr`: true
- `labels`: `$AI_MONITOR_LABEL_CONFIRM_STORY_CONDUCTOR` の値

本文とスタックの接続を終えてから付ける（先に付けると材料が揃う前に担当が動き出す）。

### 対応 story 列の反映

`## ユースケース一覧` の `対応 story` 列の `未作成` を作成した `#番号` に置き換える。

MCP `update_body` を呼ぶ:
- `number`: $number
- `is_pr`: true
- `body`: 更新した本文

### 完了報告の Resolve と作成結果の記録

complex-scenario-writer の完了報告コメントがある場合、MCP `resolve_comments` で Resolve する（複合 UC 影響なしの経路では省略する）。

続けて MCP `comment` を呼ぶ（待機なし）:
- `number`: $number
- `is_pr`: true
- `sender`: `epic-conductor`
- `receiver`: ユーザーログイン名
- `format`:
  - `type`: `plain`
  - `body`: 作成結果（story PR のリンク一覧）

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
