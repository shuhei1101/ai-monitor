# SA変更確定

承認された SA 変更を subsystem Issue 本文に反映し、修正用 PR の作成へ進む。

## 手順

### 本文の更新

承認された変更案で `## システム要件（SA）` を書き換える。

MCP `update_body` を呼ぶ:
- `number`: $issue_number
- `is_pr`: false
- `body`: 更新後本文

### 修正用 PR の作成と委任

「バグ修正着手」の「修正用 PR の作成」以降の手順をそのまま実行する（監視面の登録・バグ内容コメントへの返信と Resolve・architect への一式委任・ラベル除去・作業完了報告）。
