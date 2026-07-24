# OTel バックエンド PoC

OpenTelemetry のバックエンドを 3 候補（Jaeger / Loki + Grafana / SigNoz）で並行評価するための PoC 環境。
それぞれ `docker compose up -d` で起動し、`emit_sample.py` で Traces / Metrics / Logs のサンプルを送信して UI での見え方を確認する。

対応シナリオ: [ログ確認](../../docs/wiki/設計図/シナリオ/単一ユースケース/ログ確認.md)
外部ライブラリ: [OpenTelemetry Python SDK](../../docs/wiki/外部ライブラリ/opentelemetry.md)

## 候補比較（起動前の一次判断）

| 候補 | 対象 telemetry | コンテナ数 | UI | 特徴 |
| --- | --- | --- | --- | --- |
| [Jaeger](./jaeger/) | Traces のみ | 1 | `http://localhost:16686` | 単一コンテナで軽い。トレース専用の老舗 |
| [Loki + Grafana](./loki/) | Logs（拡張で Traces / Metrics も）| 3 | `http://localhost:3000` | ログ特化・軽量。Grafana でダッシュボード自作可 |
| [SigNoz](./signoz/) | Logs + Traces + Metrics 統合 | 8 前後 | `http://localhost:3301` | OTel ネイティブの統合オールインワン。UI が用途別に整備済み |

## 起動前提

- Docker Desktop / Docker Engine が稼働している
- WSL2 環境の場合、Docker Desktop の WSL Integration が有効
- **3 候補は OTLP gRPC ポート `4317` が競合するため、同時起動不可**。1 個ずつ立てて評価する

## 各候補の起動

### Jaeger

```bash
cd poc/otel-backends/jaeger
docker compose up -d
# UI: http://localhost:16686
docker compose down
```

### Loki + Grafana

```bash
cd poc/otel-backends/loki
docker compose up -d
# UI: http://localhost:3000 （admin / admin）
# Explore → datasource: Loki → クエリ例: {service_name="ai-monitor-poc"}
docker compose down
# データも消す場合: docker compose down -v
```

### SigNoz

公式リポジトリの Docker Compose をそのまま使う（保守負担ゼロ方針）:

```bash
cd poc/otel-backends/signoz
git clone --depth 1 https://github.com/SigNoz/signoz.git
cd signoz/deploy/docker
docker compose -p signoz-poc up -d
# UI: http://localhost:3301（初回起動時にアカウント作成画面）
docker compose -p signoz-poc down
```

詳細は [signoz/README.md](./signoz/) 参照。

## テスト送信（emit_sample.py）

3 バックエンド共通で使う Python サンプル送信スクリプト。
Traces（2 段ネスト Span）/ Metrics（Counter + Histogram）/ Logs（info/warning/error）を 1 発で送る。

### 依存の追加（初回のみ）

```bash
uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
```

### 実行

各バックエンドを起動した状態で:

```bash
# デフォルト（http://localhost:4317 に送信）
uv run python poc/otel-backends/emit_sample.py

# サービス名を切り替え（UI で識別しやすくする）
OTEL_SERVICE_NAME=ai-monitor-poc-jaeger uv run python poc/otel-backends/emit_sample.py
OTEL_SERVICE_NAME=ai-monitor-poc-loki   uv run python poc/otel-backends/emit_sample.py
OTEL_SERVICE_NAME=ai-monitor-poc-signoz uv run python poc/otel-backends/emit_sample.py
```

### 環境変数

| 変数 | デフォルト | 説明 |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | 送信先 Collector（gRPC） |
| `OTEL_SERVICE_NAME` | `ai-monitor-poc` | `service.name` resource 属性 |
| `OTEL_INSECURE` | `true` | TLS を無効化するか |

## 選定判断の観点

| 観点 | 見るポイント |
| --- | --- |
| セットアップの簡単さ | `docker compose up -d` から UI アクセスまでの所要時間 / エラー頻度 |
| 統合 UI の使いやすさ | Traces / Logs / Metrics を横断できるか。フィルタ・検索が直感的か |
| Traces の可視化 | Span 親子ツリー / Flame Graph / タイムライン |
| Logs の可視化 | 時系列表示 / attribute での絞り込み / ログレベル分離 |
| Metrics の可視化 | 時系列グラフ / パーセンタイル / ダッシュボード作成の容易さ |
| リソース消費 | コンテナのメモリ / CPU 使用量（`docker stats`） |
| 学習コスト | UI 初見での迷いにくさ / 公式ドキュメントの充実度 |

## PoC 完了後

- 選定したバックエンドを `docs/wiki/外部ライブラリ/{選定}.md` として詳細ドキュメント化する
- 選外の PoC ディレクトリはそのまま残す（将来の再評価に備えて）
