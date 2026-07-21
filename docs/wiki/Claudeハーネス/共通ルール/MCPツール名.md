# MCPツール名

手順書に出てくる `MCP {ツール名}`（例: `MCP get_issue_or_pr` / `MCP resolve_comments`）は、実行時に以下の完全名で解決する。

## 完全名の形式

```
mcp__plugin_ai-monitor_ai-monitor-tools__{ツール名}
```

例:

- `MCP get_issue_or_pr` → `mcp__plugin_ai-monitor_ai-monitor-tools__get_issue_or_pr`
- `MCP resolve_comments` → `mcp__plugin_ai-monitor_ai-monitor-tools__resolve_comments`
- `MCP add_labels` → `mcp__plugin_ai-monitor_ai-monitor-tools__add_labels`

## ToolSearch での取得

MCP ツールは deferred なので、初回使用前に `ToolSearch` で完全名を渡してスキーマをロードする（複数のツールをカンマ区切りで一括ロード可）:

```
ToolSearch(query: "select:mcp__plugin_ai-monitor_ai-monitor-tools__get_issue_or_pr,mcp__plugin_ai-monitor_ai-monitor-tools__list_addressed_comments,mcp__plugin_ai-monitor_ai-monitor-tools__resolve_comments,...")
```

## 禁則

- **完全名の推測はしない**（`mcp__ai-monitor-tools__*` や `mcp__plugin_ai-monitor__*` は誤りで、ToolSearch でヒットしない）
- **`gh` CLI で MCP ツールを代替しない**（コメント Resolve / ラベル遷移 等は MCP ツール経由で行う。gh 直叩きだと Resolve が漏れる 等の不整合が起きる）
