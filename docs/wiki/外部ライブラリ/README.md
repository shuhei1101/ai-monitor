---
template_version: 1.0.0
---

# 外部ライブラリ

採用済みの外部ライブラリ / 外部ツールのインデックス。
書き方規約は `テンプレート/外部ライブラリ.md` 参照。

## 一覧

| ライブラリ | リンク | 用途 | 補足 |
| --- | --- | --- | --- |
| githubkit | [githubkit](./githubkit.md) | エージェント / モニターの GitHub 操作（REST + GraphQL） | - |
| FastAPI | [FastAPI](./fastapi.md) | モニター本体のアプリ基盤（HTTP 受信 + lifespan でのループ駆動） | 起動サーバーは uvicorn |
| gh（GitHub CLI） | [gh](./gh.md) | セッションフックのリポジトリ情報取得 | Python ライブラリではなく CLI |
| tmux | [tmux](./tmux.md) | エージェントセッションの実体操作（作成 / 送信 / 生存確認 / kill） | Python ライブラリではなく CLI |
| OpenTelemetry Python SDK | [opentelemetry](./opentelemetry.md) | モニター / エージェントから telemetry（Traces / Metrics / Logs）を Collector に送信 | `opentelemetry-api` + `opentelemetry-sdk` + `opentelemetry-exporter-otlp` のセット |
| OpenTelemetry Collector | [opentelemetry-collector](./opentelemetry-collector.md) | OTLP 受信 + Loki / 他バックエンドへ転送する中継バイナリ | contrib ディストリビューションを Docker Compose 1 サービスで起動 |
| Grafana Loki | [loki](./loki.md) | telemetry の Log 保存・検索バックエンド | OTel Collector 経由で受信、LogQL で検索 |
| Grafana | [Grafana](./grafana.md) | telemetry の可視化 UI（Loki / Prometheus / Tempo 等を横断表示） | Docker Compose で単体起動 + datasource プロビジョニング |
