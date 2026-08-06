# RE完了確認

依頼先が commit した現状の設計書を確認し、起こし漏れがないかをユーザーに確認する。
`{自分}` / `{成果物}` はフェーズ索引の担当範囲表の値に読み替える。

## 手順

### base の面の確認

初期処理で取得した `parent`（RE PR の base ブランチを head に持つ面）の `state` を見る。

`closed` の場合は上位が作業を畳んだ後なので、起こした成果物を引き取る面が無い。
マージせず RE PR を畳んで手番を返す（以降の手順は実行しない）。

1. MCP `comment` を呼ぶ（`number`: RE PR の番号・`is_pr`: true・`sender`: `{自分}`・`receiver`: ユーザーログイン名・`format`: `type` が `plain` で `body` が base の面が closed のため RE をマージせず畳む旨と、起こした成果物へのリンク）
2. MCP `close` を呼ぶ（`number`: RE PR の番号・`reason`: `not_planned`・`delete_branch`: true）
3. MCP `remove_watch_targets` を呼ぶ（`agent_name`: `{自分}`・`number`: $number・`watch_numbers`: RE PR の番号）
4. MCP `report_completion` を呼ぶ（`agent_name`: `{自分}`・`number`: RE PR の番号）

成果物は closed PR の diff に残るので、上位が再開したときに読み直せる。

### 起こされたページの確認

RE ブランチの worktree（`.claude/worktrees/{ブランチ名の / を - に置換}`）へ移動し、`git pull --ff-only` でリモートの最新を取り込む。

commit された `{成果物}` と、完了報告コメントの内容・読み取れなかった箇所を読む。

続けて RE PR 本文の `## タスク一覧` が全行 `[x]` になっていることを確認する。
チェックを入れるのは起こした依頼先なので、ここでは本文を書き換えない。

- 未チェックのまま残っている場合、完了報告コメントに追記して指摘し、チェックを入れてもらう（自分では入れない）

### 最終確認コメントの投稿

MCP `comment` を呼ぶ:
- `number`: RE PR の番号
- `is_pr`: true
- `sender`: `{自分}`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `format`:
  - `type`: `plain`
  - `body`: 起こしたページ一覧 + 完了報告に添えられた内容の要約 + 読み取れなかった箇所 + 起こし漏れの指摘方法と承認方法の案内

### 議論中 付与 + 待機

MCP `add_labels` を呼ぶ:
- `number`: RE PR の番号
- `is_pr`: true
- `labels`:
  - `$AI_MONITOR_LABEL_IN_DISCUSSION` の値

続けて MCP `set_assignee` を呼ぶ:
- `number`: RE PR の番号
- `is_pr`: true

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `{自分}`
- `number`: RE PR の番号
