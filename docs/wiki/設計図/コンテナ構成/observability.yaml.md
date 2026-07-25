---
template_version: 1.1.0
---

# observability.yaml

OpenTelemetry の Log を集約する観測基盤スタック。
モニター / エージェント → OTel Collector → Loki → Grafana の経路で telemetry を受信・保存・可視化する。

配置: `deploy/observability/observability.yaml`

Compose file specification: <https://docs.docker.com/compose/compose-file/>

## サービス一覧

| サービス名 | イメージ | 用途 | 公開ポート | 依存 | 補足 |
| --- | --- | --- | --- | --- | --- |
| [otel-collector](#otel-collector) | `otel/opentelemetry-collector-contrib:0.113.0` | OTLP 受信 + Loki 転送 | `4317` / `4318` | loki | OTLP gRPC / HTTP |
| [loki](#loki) | `grafana/loki:3.2.1` | Log 保存 + LogQL 提供 | `3100` | - | 単一バイナリ + filesystem storage |
| [grafana](#grafana) | `grafana/grafana:11.3.0` | 可視化 UI（Explore / Dashboards）| `3000` | loki | admin / admin |

## otel-collector
> 設定ファイル: `./otel-collector-config.yaml`

[OpenTelemetry Collector](../../外部ライブラリ/opentelemetry-collector.md) の中継サーバー。
OTLP プロトコル（gRPC / HTTP）で受信した telemetry を Loki の `/loki/api/v1/push` に転送する。
Log 以外（Traces / Metrics）は現時点では debug exporter に流して破棄する（将来 Tempo / Prometheus を追加したら差し替える）。

| 項目 | 値 | 補足 |
| --- | --- | --- |
| イメージ | `otel/opentelemetry-collector-contrib:0.113.0` | - |
| ビルド | `-` | - |
| コンテナ名 | `ai-monitor-collector` | - |
| 公開ポート | `4317:4317` / `4318:4318` | OTLP gRPC / HTTP |
| コマンド | `--config=/etc/otelcol-contrib/config.yaml` | - |
| 依存 | `loki` | Loki 起動後に受付開始 |
| リスタート | `unless-stopped` | - |

### ボリューム

| ソース | マウント先 | モード | 補足 |
| --- | --- | --- | --- |
| `./otel-collector-config.yaml` | `/etc/otelcol-contrib/config.yaml` | `ro` | bind mount（設定ファイル） |

## loki
> 設定ファイル: `./loki-config.yaml`

[Grafana Loki](../../外部ライブラリ/loki.md) による Log の保存と LogQL クエリを提供するバックエンド。
単一バイナリ + filesystem storage の開発向け構成（本番規模では object storage + マイクロサービス構成に切り替え）。

| 項目 | 値 | 補足 |
| --- | --- | --- |
| イメージ | `grafana/loki:3.2.1` | - |
| ビルド | `-` | - |
| コンテナ名 | `ai-monitor-loki` | - |
| 公開ポート | `3100:3100` | Loki HTTP（クエリ / push） |
| コマンド | `-config.file=/etc/loki/loki-config.yaml` | - |
| 依存 | `-` | - |
| リスタート | `unless-stopped` | - |

### ボリューム

| ソース | マウント先 | モード | 補足 |
| --- | --- | --- | --- |
| `./loki-config.yaml` | `/etc/loki/loki-config.yaml` | `ro` | bind mount（設定ファイル） |
| `loki-data` | `/loki` | `rw` | named volume（chunks / index の永続化） |

## grafana
> 設定ファイル: `./grafana-datasources.yaml`

[Grafana](../../外部ライブラリ/grafana.md) による可視化 UI。
Loki datasource を自動プロビジョニングし、Explore で LogQL アドホック検索、Dashboards で保存ダッシュボードを提供する。

| 項目 | 値 | 補足 |
| --- | --- | --- |
| イメージ | `grafana/grafana:11.3.0` | - |
| ビルド | `-` | - |
| コンテナ名 | `ai-monitor-grafana` | - |
| 公開ポート | `3000:3000` | Grafana UI |
| コマンド | `-` | 既定 entrypoint |
| 依存 | `loki` | datasource として Loki を自動プロビジョニング |
| リスタート | `unless-stopped` | - |

### 環境変数

| 環境変数 | 値 | 補足 |
| --- | --- | --- |
| `GF_SECURITY_ADMIN_USER` | `admin` | 開発デフォルト（本番は環境ごとに置換） |
| `GF_SECURITY_ADMIN_PASSWORD` | `admin` | 開発デフォルト（本番は環境ごとに置換） |
| `GF_AUTH_ANONYMOUS_ENABLED` | `false` | 認証必須（匿名アクセス禁止） |

### ボリューム

| ソース | マウント先 | モード | 補足 |
| --- | --- | --- | --- |
| `./grafana-datasources.yaml` | `/etc/grafana/provisioning/datasources/datasources.yaml` | `ro` | datasource 自動プロビジョニング |
| `grafana-data` | `/var/lib/grafana` | `rw` | named volume（ダッシュボード / 設定の永続化） |
