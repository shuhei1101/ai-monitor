# REマージ

ユーザー承認を受けて RE PR を master へマージし、現状のアーキテクチャ図を構成確定の入力にする。

## 手順

### 一括 Resolve

MCP `resolve_comments` を呼ぶ:
- `node_ids`: RE PR の自分宛コメントの `node_id` 配列

### マージ

RE ブランチの worktree へ移動し、`git pull --ff-only` でリモートの最新を取り込む。
`規約/マージ手順.md` に沿って base（`master`）を取り込み、コンフリクトがないことを確認する。

- コンフリクトが発生した場合、RE PR に競合ファイルとどちらを残すかの相談コメントを投稿し、`議論中` 付与 + `assignee=ユーザー` で待機する（解消の往復は「応答ループ」で回し、全競合解消後に本手順へ合流する）

MCP `merge_pr` を呼ぶ:
- `pr_number`: RE PR の番号
- `strategy`: `squash`

続けて MCP `worktree_remove` を呼ぶ:
- `branch`: RE ブランチ

### 監視面からの除去

構成確定へ続くため、ここで除去するのは RE PR の番号だけにする（system Issue は最上位なので、監視面の全除去は system Issue の完了時に行う）。

MCP `remove_watch_targets` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: $issue_number
- `watch_numbers`: RE PR の番号

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `system-conductor`
- `number`: RE PR の番号
