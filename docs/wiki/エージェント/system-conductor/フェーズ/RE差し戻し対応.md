# RE差し戻し対応

architecture-reverse-engineer が担当範囲の実装を見つけられなかった報告を受け、担当範囲の見直しかリバースエンジニアリングなしで進めるかをユーザーに相談する。

## 手順

### 差し戻し内容の確認

未解決の自分宛コメントの差し戻し報告から、探した範囲と見つからなかった理由を読む。

### 相談コメントの投稿

MCP `comment` を呼ぶ:
- `number`: RE PR の番号
- `is_pr`: true
- `sender`: `system-conductor`
- `receiver`: ユーザーログイン名（`gh api user --jq '.login'` で取得）
- `format`:
  - `type`: `plain`
  - `body`: 差し戻しの経緯 + 担当範囲の見直し案とリバースエンジニアリングなしで進める案の比較 + 推奨と理由

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
- `agent_name`: `system-conductor`
- `number`: RE PR の番号
