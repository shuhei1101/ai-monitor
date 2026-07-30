# ライブラリPoC結果まとめ

library-poc-runner の検証結果を集約し、subsystem PR で採用判断を仰ぐ。
本フェーズは PoC PR の完了報告で起動するため、ラベル操作と作業完了報告の対象は起動要因になった PoC PR になる。

## 手順

### 検証結果の確認と Resolve

完了報告コメントと PoC PR 本文の `## 検証観点と結果` / `## 最小再現コード` を読み、成功条件に対する実測値と判定を確認する。

MCP `resolve_comments` を呼ぶ:
- `node_ids`: library-poc-runner の完了報告コメントの `node_id`

### PoC PR のラベル除去

MCP `transition_phase` を呼ぶ:
- `number`: 完了報告を受け取った PoC PR の番号
- `is_pr`: true
- `remove_labels_`:
  - `$AI_MONITOR_LABEL_CONFIRM_ARCHITECT` の値
- `add_labels_`: なし

### 結果まとめの投稿 + 待機

未報告の PoC PR が残っている場合は投稿せず、「作業完了報告」を実行して自ターンを終える（全候補の結果が揃ってからまとめる）。

MCP `comment` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `sender`: `architect`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `format`:
  - `type`: `plain`
  - `body`: 全候補の結果まとめ（候補 / 観点 / 実測値 / 判定の表 + PoC PR リンク + 推奨候補と理由 + 採用決定・追加検証の依頼方法の案内）

- 追加検証の結果で既存の結果まとめを更新する場合、`comment` ではなく MCP `reply_comment`（`comment_node_id`: 結果まとめコメントの node_id）で更新後の表を追記する

続けて MCP `add_labels` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_IN_DISCUSSION` の値

続けて MCP `set_assignee` を呼ぶ:
- `number`: $pr_number
- `is_pr`: true

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `architect`
- `number`: 完了報告を受け取った PoC PR の番号
