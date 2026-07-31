# REマージ

ユーザー承認を受けて RE PR を base へマージし、現状の設計書を自レイヤーの要件確定の入力にする。
`{自分}` / `{base}` はフェーズ索引の担当範囲表の値に読み替える。

## 手順

### 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: RE PR の自分宛コメントの `node_id` 配列

### Draft 解除

MCP `mark_pr_ready` を呼ぶ:
- `pr_number`: RE PR の番号

Draft のままマージすると 405 で失敗する。
Ready 済みの PR に呼んでも何も起きない。

### マージ

RE ブランチの worktree へ移動し、`git pull --ff-only` でリモートの最新を取り込む。
`規約/マージ手順.md` に沿って base（`{base}`）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、RE PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: RE PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: RE ブランチ

### 監視面からの除去

要件確定へ続くため、ここで除去するのは RE PR の番号だけにする（監視面の全除去は最終マージのときに行う。共通ルール『最終マージの判定』）。

MCP `remove_watch_targets` を呼ぶ:
- `agent_name`: `{自分}`
- `number`: $issue_number
- `watch_numbers`: RE PR の番号

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `{自分}`
- `number`: RE PR の番号
