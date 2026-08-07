# RE中止

「リバースエンジニアリングなしで進める」が選ばれたとき、RE PR を成果物なしで畳んで自レイヤーの通常フローへ戻す。
`{自分}` / `{RE ブランチ}` / `{レイヤーラベル}` はフェーズ索引の担当範囲表の値に読み替える。

## 手順

### 決定の確認

『RE差し戻し対応』で投稿した相談スレッドの返信から、選ばれた案を読む。

- 「担当範囲の見直し」が選ばれた場合は本フェーズを実行しない（『リバースエンジニアリング起動』の「作成依頼」で範囲を変えて再依頼する）
- ユーザーが案を選ばずに `議論中` だけを外した場合は、相談コメントで推奨した案を採る

推奨案を採った場合は、そのことをスレッドへ返信追記してから次へ進む。

MCP `reply_comment` を呼ぶ:
- `comment_node_id`: 相談スレッドの node_id
- `sender`: `{自分}`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `format`:
  - `type`: `plain`
  - `body`: 推奨案（リバースエンジニアリングなしで進める）を採って RE を中止する旨

### RE PR のクローズ

MCP `close` を呼ぶ:
- `number`: RE PR の番号
- `is_pr`: true
- `delete_branch`: true

### worktree の削除

MCP `worktree_remove` を呼ぶ:
- `branch`: `{RE ブランチ}`

### 監視面の除去

MCP `remove_watch_targets` を呼ぶ:
- `agent_name`: `{自分}`
- `number`: $number
- `watch_numbers`: RE PR の番号

### リバースエンジニアリングラベルの除去

以降のターンで RE 系フェーズへ入らないよう、自面から `リバースエンジニアリング` を外す。

MCP `remove_labels` を呼ぶ:
- `number`: $number
- `is_pr`: 自面が PR なら true
- `labels`:
  - `$AI_MONITOR_LABEL_REVERSE_ENGINEERING` の値

### 手番の引き戻し

RE PR に持たせていた手番を自面へ戻す。
次のターンは自レイヤーの通常フロー（要件確定・構成確定）に入る。

MCP `add_labels` を呼ぶ:
- `number`: $number
- `is_pr`: 自面が PR なら true
- `labels`:
  - `確認:{自分}`（`AI_MONITOR_LABEL_CONFIRM_*`）の値

### 作業完了報告

MCP `report_completion` を呼ぶ:
- `agent_name`: `{自分}`
- `number`: $number
