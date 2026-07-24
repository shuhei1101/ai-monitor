---
template_version: 1.0.0
---

# OpenTelemetry Python SDK

Python アプリから telemetry（Traces / Metrics / Logs）を計装して OTel Collector に送信する SDK 群。

「言語共通の API 仕様」「実装」「送信 Exporter」「Resource 属性」の 4 パーツを組み合わせて使う。
本ページでは Python 向けに提供される `opentelemetry-*` パッケージを 1 ページに集約する。

## 現在のバージョン情報

| 項目 | 内容 | 補足 |
| --- | --- | --- |
| バージョン | `opentelemetry-api` / `opentelemetry-sdk` / `opentelemetry-exporter-otlp` すべて `1.44.0` | 2026-07-24 時点最新 |
| ライセンス | Apache-2.0 | - |
| 公式 URL | https://github.com/open-telemetry/opentelemetry-python | - |
| 公式ドキュメント | https://opentelemetry.io/docs/languages/python/ | - |

## インストール手順

```bash
uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

Exporter は用途に応じて内訳を選ぶ:

| パッケージ | 用途 | 補足 |
| --- | --- | --- |
| `opentelemetry-exporter-otlp` | 依存メタパッケージ | gRPC / HTTP 両方を入れる |
| `opentelemetry-exporter-otlp-proto-grpc` | OTLP over gRPC 送信 | ローカル Collector（4317 番）向け |
| `opentelemetry-exporter-otlp-proto-http` | OTLP over HTTP 送信 | ネットワーク経由（4318 番）向け |

auto-instrumentation を使う場合は別途:

```bash
uv add opentelemetry-instrumentation-logging opentelemetry-instrumentation-requests
```

## API 一覧

バージョン: `1.29.0`

| 種別 | 名前 | 用途 | 補足 |
| --- | --- | --- | --- |
| クラス | [`Resource`](#resource) | telemetry の共通属性（`service.name` 等）を保持 | Provider に必ず渡す |
| クラス | [`LoggerProvider`](#loggerprovider) | Log レコードのプロバイダ | プロセス起動時に 1 回だけ生成 |
| クラス | [`LoggingHandler`](#logginghandler) | Python 標準 `logging` を OTel に橋渡し | root logger に addHandler して自動送信 |
| クラス | [`BatchLogRecordProcessor`](#batchlogrecordprocessor) | Log レコードをバッチで Exporter に流す | LoggerProvider に登録 |
| クラス | [`OTLPLogExporter`](#otlplogexporter) | Log レコードを OTLP プロトコルで送信 | gRPC / HTTP どちらか |
| クラス | [`TracerProvider`](#tracerprovider) | Span のプロバイダ | プロセス起動時に 1 回だけ生成 |
| クラス | [`BatchSpanProcessor`](#batchspanprocessor) | Span をバッチで Exporter に流す | TracerProvider に登録 |
| クラス | [`OTLPSpanExporter`](#otlpspanexporter) | Span を OTLP プロトコルで送信 | - |
| 関数 | [`trace.get_tracer()`](#traceget_tracer) | Tracer を取得 | Span 発行の入口 |
| メソッド | [`tracer.start_as_current_span()`](#tracerstart_as_current_span) | Span を開始してコンテキストに紐付け | with 文で使う |
| クラス | [`MeterProvider`](#meterprovider) | メトリクスのプロバイダ | プロセス起動時に 1 回だけ生成 |
| クラス | [`PeriodicExportingMetricReader`](#periodicexportingmetricreader) | 定期間隔でメトリクスを Exporter に流す | MeterProvider に登録 |
| クラス | [`OTLPMetricExporter`](#otlpmetricexporter) | メトリクスを OTLP プロトコルで送信 | - |
| 関数 | [`metrics.get_meter()`](#metricsget_meter) | Meter を取得 | メトリクス発行の入口 |
| メソッド | [`meter.create_counter()`](#metercreate_counter) | カウンタ計器を作る | 単調増加値の計測用 |
| メソッド | [`meter.create_histogram()`](#metercreate_histogram) | ヒストグラム計器を作る | 分布・パーセンタイル計測用 |

### `Resource`

telemetry に付与する共通属性（サービス名・環境・ホスト等）を保持するイミュータブルなクラス。
Provider（Logger / Tracer / Meter）を作るときに必ず渡す。

#### パラメータ（`Resource.create()`）

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `attributes` | `dict[str, str]` | 必須 | - | 属性キー / 値のマップ | セマンティック規約準拠のキーが推奨 |
| `attributes.service.name` | `str` | 必須 | - | サービス識別名 | UI 上のフィルタキーになる |
| `attributes.service.namespace` | `str` | 任意 | - | サービス空間 | 複数サービスをグループ化 |
| `attributes.service.instance.id` | `str` | 任意 | - | インスタンス識別子 | プロセス単位で一意にする |
| `attributes.deployment.environment` | `str` | 任意 | - | 環境名 | `dev` / `staging` / `prod` 等 |

パラメータ例:

```python
from opentelemetry.sdk.resources import Resource

resource = Resource.create({
    "service.name": "ai-monitor",
    "service.namespace": "monitor",
    "deployment.environment": "dev",
})
```

### `LoggerProvider`

Log レコードのプロバイダ。
`BatchLogRecordProcessor` を登録するとバッチ送信が有効化される。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `resource` | `Resource` | 必須 | - | 共通属性 | `Resource.create()` で作った物 |

パラメータ例:

```python
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider

provider = LoggerProvider(resource=resource)
set_logger_provider(provider)
```

### `LoggingHandler`

Python 標準 `logging` を OpenTelemetry Log にブリッジする `logging.Handler`。
root logger に `addHandler` するだけで、既存の `logger.info(...)` などが Collector に流れる。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `level` | `int` | 任意 | `logging.NOTSET` | 転送するログレベル | `logging.INFO` 等 |
| `logger_provider` | `LoggerProvider` | 任意 | グローバル取得 | 使用する Provider | 明示指定推奨 |

パラメータ例:

```python
import logging
from opentelemetry.sdk._logs import LoggingHandler

handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)
```

### `BatchLogRecordProcessor`

Log レコードをキューに溜めて定期・満杯タイミングで Exporter に流す。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `exporter` | `LogExporter` | 必須 | - | 送信先 | `OTLPLogExporter` を渡す |
| `max_queue_size` | `int` | 任意 | `2048` | キュー上限 | 超えると古いものから捨てる |
| `schedule_delay_millis` | `int` | 任意 | `5000` | フラッシュ間隔 (ms) | 5 秒間隔で送信 |
| `max_export_batch_size` | `int` | 任意 | `512` | 1 回の送信上限 | - |

パラメータ例:

```python
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

processor = BatchLogRecordProcessor(exporter)
provider.add_log_record_processor(processor)
```

### `OTLPLogExporter`

Log レコードを OTLP プロトコルで Collector に送信する Exporter。
gRPC 版と HTTP 版があり、パッケージインポート先で切り替える（`opentelemetry.exporter.otlp.proto.grpc._log_exporter` / `.proto.http._log_exporter`）。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `endpoint` | `str` | 任意 | `http://localhost:4317`（gRPC）/ `http://localhost:4318/v1/logs`（HTTP）| 送信先 URL | Collector の受信ポート |
| `insecure` | `bool` | 任意 | `False` | TLS を無効化 | ローカル通信では `True` |
| `headers` | `dict[str, str]` | 任意 | `None` | HTTP ヘッダー | 認証用 |
| `timeout` | `int` | 任意 | `10` | 送信タイムアウト (秒) | - |

パラメータ例:

```python
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

exporter = OTLPLogExporter(endpoint="http://localhost:4317", insecure=True)
```

### `TracerProvider`

Span のプロバイダ。
`BatchSpanProcessor` を登録するとバッチ送信が有効化される。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `resource` | `Resource` | 必須 | - | 共通属性 | - |

パラメータ例:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)
```

### `BatchSpanProcessor`

Span をキューに溜めてバッチ送信する。パラメータは [`BatchLogRecordProcessor`](#batchlogrecordprocessor) と同型。

パラメータ例:

```python
from opentelemetry.sdk.trace.export import BatchSpanProcessor

processor = BatchSpanProcessor(exporter)
provider.add_span_processor(processor)
```

### `OTLPSpanExporter`

Span を OTLP プロトコルで送信する Exporter。パラメータは [`OTLPLogExporter`](#otlplogexporter) と同型。

パラメータ例:

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
```

### `trace.get_tracer()`

指定名前空間の Tracer を取得する。呼び出し側モジュールで 1 回取得して使い回す想定。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `instrumenting_module_name` | `str` | 必須 | - | 呼び出し元モジュール名 | `__name__` を渡すのが定石 |
| `instrumenting_library_version` | `str` | 任意 | `""` | ライブラリ版 | 独自計装のバージョン管理用 |

パラメータ例:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)
```

#### 戻り値

| 型 | 説明 | 補足 |
| --- | --- | --- |
| `Tracer` | Span を発行するオブジェクト | 以降 `start_as_current_span` 等で使う |

### `tracer.start_as_current_span()`

Span を開始してカレントコンテキストに紐付ける。with 文で使うのが定石。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `name` | `str` | 必須 | - | Span 名 | 「関数名」相当 |
| `attributes` | `dict[str, Any]` | 任意 | `None` | Span 属性 | フィルタ・グルーピング用 |
| `kind` | `SpanKind` | 任意 | `INTERNAL` | Span 種別 | `SERVER` / `CLIENT` / `PRODUCER` / `CONSUMER` / `INTERNAL` |

パラメータ例:

```python
with tracer.start_as_current_span("polling_iteration", attributes={"project": "sandbox"}) as span:
    span.set_attribute("issue.number", 123)
    # 何か処理
```

### `MeterProvider`

メトリクス（Counter / Histogram 等）のプロバイダ。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `resource` | `Resource` | 必須 | - | 共通属性 | - |
| `metric_readers` | `list[MetricReader]` | 必須 | - | 読み取り + 送信を担うリーダー | `PeriodicExportingMetricReader` を渡す |

パラメータ例:

```python
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider

provider = MeterProvider(resource=resource, metric_readers=[reader])
metrics.set_meter_provider(provider)
```

### `PeriodicExportingMetricReader`

一定間隔でメトリクス値を Exporter に流す Reader。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `exporter` | `MetricExporter` | 必須 | - | 送信先 | `OTLPMetricExporter` を渡す |
| `export_interval_millis` | `int` | 任意 | `60000` | 送信間隔 (ms) | デフォルト 60 秒 |

パラメータ例:

```python
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

reader = PeriodicExportingMetricReader(exporter, export_interval_millis=15000)
```

### `OTLPMetricExporter`

メトリクスを OTLP プロトコルで送信する Exporter。パラメータは [`OTLPLogExporter`](#otlplogexporter) と同型。

パラメータ例:

```python
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

exporter = OTLPMetricExporter(endpoint="http://localhost:4317", insecure=True)
```

### `metrics.get_meter()`

指定名前空間の Meter を取得する。使い方は [`trace.get_tracer()`](#traceget_tracer) と同型。

パラメータ例:

```python
from opentelemetry import metrics

meter = metrics.get_meter(__name__)
```

### `meter.create_counter()`

単調増加値（総数）を計測するカウンタを作る。

#### パラメータ

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `name` | `str` | 必須 | - | メトリクス名 | 例: `agent.session.started` |
| `unit` | `str` | 任意 | `""` | 単位 | `1` / `s` / `ms` 等 |
| `description` | `str` | 任意 | `""` | 説明 | UI に表示 |

パラメータ例:

```python
counter = meter.create_counter("agent.session.started", unit="1", description="起動したエージェントセッション数")
counter.add(1, {"agent": "single-scenario-writer"})
```

### `meter.create_histogram()`

分布（パーセンタイル / 平均）を計測するヒストグラムを作る。パラメータは [`meter.create_counter()`](#metercreate_counter) と同型。

パラメータ例:

```python
histogram = meter.create_histogram("agent.turn.duration", unit="s", description="1 ターンの処理時間")
histogram.record(elapsed_sec, {"agent": "single-scenario-writer"})
```
