---
template_version: 2.0.0
---

# 外部ライブラリ

採用済みの外部ライブラリ / 外部ツールのインデックス。
書き方規約は `テンプレート/外部ライブラリ.md` 参照。

## 目次

| ページ | 概要 | 使用箇所 | 補足 |
| --- | --- | --- | --- |
| [githubkit](./githubkit.md) | エージェント / モニターの GitHub 操作（REST + GraphQL） | `src/ai_monitor/integrations/github/` | - |
| [FastAPI](./fastapi.md) | モニター本体のアプリ基盤（HTTP 受信 + lifespan でのループ駆動） | `src/ai_monitor/server/` | 起動サーバーは uvicorn |
| [gh（GitHub CLI）](./gh.md) | エージェント手順でのユーザーログイン名の取得 | `docs/wiki/エージェント/*/フェーズ/` | Python ライブラリではなく CLI。GitHub の操作自体は MCP に限定（共通ルール『MCPツール名』） |
| [tmux](./tmux.md) | エージェントセッションの実体操作（作成 / 送信 / 生存確認 / kill） | `src/ai_monitor/integrations/tmux/` | Python ライブラリではなく CLI |
| [OpenTelemetry Python SDK](./opentelemetry.md) | モニター / エージェントから telemetry（Traces / Metrics / Logs）を Collector に送信 | `src/ai_monitor/observability/` | `opentelemetry-api` + `opentelemetry-sdk` + `opentelemetry-exporter-otlp` のセット |
