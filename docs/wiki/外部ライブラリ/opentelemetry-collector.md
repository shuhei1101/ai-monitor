---
template_version: 1.0.0
---

# OpenTelemetry Collector

OTLP プロトコルで受信した telemetry（Traces / Metrics / Logs）を任意のバックエンドへ中継する独立バイナリ。
YAML 設定ファイル 1 枚で `receivers → processors → exporters` のパイプラインを組み立てて駆動する。
本ページは `contrib` ディストリビューション（Loki など公式外の exporter を同梱）を対象とする。

## 現在のバージョン情報

| 項目 | 内容 | 補足 |
| --- | --- | --- |
| バージョン | `otel/opentelemetry-collector-contrib:0.113.0` | 2026-07-24 時点最新 |
| ライセンス | Apache-2.0 | - |
| 公式 URL | https://github.com/open-telemetry/opentelemetry-collector-contrib | - |
| 公式ドキュメント | https://opentelemetry.io/docs/collector/ | - |

## インストール手順

Docker Compose の 1 サービスとして起動する構成:

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.113.0
    container_name: otel-collector
    restart: unless-stopped
    command:
      - "--config=/etc/otelcol-contrib/config.yaml"
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml:ro
    ports:
      - "4317:4317"  # OTLP gRPC
      - "4318:4318"  # OTLP HTTP
    depends_on:
      - loki
```

- `contrib` イメージは公式コア（`otel/opentelemetry-collector`）に `loki` / `prometheusremotewrite` などのサードパーティ receiver / exporter を同梱したディストリビューション
- 設定ファイルは `--config` オプションでパスを渡す（`file:` / `env:` / `yaml:` スキーム指定で複数マージも可能）

## API 一覧

バージョン: `0.113.0`

| 種別 | 名前 | 用途 | 補足 |
| --- | --- | --- | --- |
| 設定 | [`receivers`](#receivers) | 受信コンポーネントの定義 | 対応 receiver を子キーで宣言 |
| 設定 | [`processors`](#processors) | 加工コンポーネントの定義 | パイプラインで適用順に並べる |
| 設定 | [`exporters`](#exporters) | 送信コンポーネントの定義 | バックエンド別に子キーで宣言 |
| 設定 | [`extensions`](#extensions) | 補助コンポーネントの定義 | HTTP エンドポイントなどを提供 |
| 設定 | [`service.pipelines`](#servicepipelines) | signal ごとに receivers → processors → exporters を結線 | logs / traces / metrics ごとに定義 |
| 設定 | [`service.telemetry`](#servicetelemetry) | Collector 自身のログ / メトリクス出力設定 | 自己観測 |
| receiver | [`otlp`](#otlp-receiver) | OTLP gRPC / HTTP の受信 | 4317 / 4318 |
| processor | [`batch`](#batch-processor) | バッチ送信 | ネットワーク効率化 |
| processor | [`attributes`](#attributes-processor) | Log / Span record attribute の追加・変更 | Loki ラベル昇格の指定にも使う |
| processor | [`resource`](#resource-processor) | Resource attribute の追加・変更 | サービス識別属性の付与 |
| processor | [`memory_limiter`](#memory_limiter-processor) | メモリ使用量制限 | OOM 防止 |
| exporter | [`loki`](#loki-exporter) | Grafana Loki へ Log を転送 | `/loki/api/v1/push` |
| exporter | [`otlp`](#otlp-exporter) | 他 Collector / Tempo などへ OTLP over gRPC で転送 | - |
| exporter | [`debug`](#debug-exporter) | stdout に出力して破棄 | 開発 / 検証向け |
| 挙動 | [OTLP から Loki へのラベル昇格](#otlp-から-loki-へのラベル昇格) | Collector 側から見た昇格設定 | `loki.resource.labels` / `loki.attribute.labels` |
| エンドポイント | [`GET /`](#get-)  | `health_check` extension のヘルスチェック | Compose の healthcheck 向け |
| エンドポイント | [`GET /debug/pprof/`](#get-debugpprof) | `pprof` extension のプロファイル取得 | Go 標準の pprof UI |

### `receivers`

Collector が telemetry を受信する入口の宣言セクション。
子キーに receiver 名を書き、その下に固有設定を書く（`otlp` / `prometheus` / `filelog` など）。
ここで宣言しただけでは動作せず、`service.pipelines` の各 signal で参照して初めて有効化される。

パラメータ例:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
```

### `processors`

受信した telemetry を送信前に加工するコンポーネントの宣言セクション。
`batch` / `attributes` / `resource` / `memory_limiter` などをここで宣言する。
`service.pipelines` で参照する順序が実行順序になる（`[memory_limiter, resource, attributes, batch]` のように前段の重い処理を先に置く）。

パラメータ例:

```yaml
processors:
  batch:
    send_batch_size: 1024
    timeout: 5s
  resource:
    attributes:
      - action: insert
        key: loki.resource.labels
        value: service.name,service.namespace,host.name
```

### `exporters`

加工済み telemetry を外部バックエンドへ送信するコンポーネントの宣言セクション。
バックエンドごとに子キー（`loki` / `otlp` / `prometheusremotewrite` / `debug` など）を書き、送信先 URL / 認証 / 圧縮などを設定する。

パラメータ例:

```yaml
exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
  debug:
    verbosity: basic
```

### `extensions`

パイプラインには乗らず Collector プロセス全体にサービスを提供するコンポーネントの宣言セクション。
ヘルスチェック / プロファイル / zpages などの HTTP エンドポイントを追加する。
宣言後は `service.extensions` に列挙して有効化する。

パラメータ例:

```yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
  pprof:
    endpoint: 0.0.0.0:1777

service:
  extensions: [health_check, pprof]
```

### `service.pipelines`

signal（`logs` / `traces` / `metrics`）ごとに receivers → processors → exporters を結線するセクション。
同じ receiver / processor / exporter を複数 signal から参照してよい（インスタンスは 1 つで共有される）。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `logs.receivers` | `list[str]` | 必須 | - | Log signal の入口 | `receivers` で宣言済みの名前 |
| `logs.processors` | `list[str]` | 任意 | `[]` | Log signal の加工順 | 左から順に適用 |
| `logs.exporters` | `list[str]` | 必須 | - | Log signal の出口 | 複数指定でファンアウト |
| `traces.receivers` | `list[str]` | 必須 | - | Trace signal の入口 | 同上 |
| `traces.processors` | `list[str]` | 任意 | `[]` | Trace signal の加工順 | 同上 |
| `traces.exporters` | `list[str]` | 必須 | - | Trace signal の出口 | 同上 |
| `metrics.receivers` | `list[str]` | 必須 | - | Metric signal の入口 | 同上 |
| `metrics.processors` | `list[str]` | 任意 | `[]` | Metric signal の加工順 | 同上 |
| `metrics.exporters` | `list[str]` | 必須 | - | Metric signal の出口 | 同上 |

パラメータ例:

```yaml
service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [resource, attributes, batch]
      exporters: [loki, debug]
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

### `service.telemetry`

Collector 自身が吐くログ / メトリクスの設定。
自己観測（Collector の落ち込み・エラー率の可視化）に使う。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `logs.level` | `'debug' or 'info' or 'warn' or 'error'` | 任意 | `info` | Collector のログレベル | - |
| `logs.encoding` | `'console' or 'json'` | 任意 | `console` | ログ出力形式 | 集約時は `json` |
| `metrics.level` | `'none' or 'basic' or 'normal' or 'detailed'` | 任意 | `basic` | 自己メトリクスの粒度 | `detailed` はキュー滞留も含む |
| `metrics.address` | `str` | 任意 | `0.0.0.0:8888` | Prometheus 形式の公開ポート | `/metrics` をスクレイプ |

パラメータ例:

```yaml
service:
  telemetry:
    logs:
      level: info
    metrics:
      level: basic
      address: 0.0.0.0:8888
```

### `otlp` receiver

OTLP プロトコルで telemetry を受信する receiver。
gRPC（既定 4317）と HTTP（既定 4318）の 2 プロトコルを持ち、片方だけの起動も両方同時も可能。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `protocols.grpc.endpoint` | `str` | 任意 | `0.0.0.0:4317` | gRPC 受付アドレス | コンテナ内は `0.0.0.0` bind |
| `protocols.grpc.max_recv_msg_size_mib` | `int` | 任意 | `4` | 1 メッセージの上限 (MiB) | 巨大 Span 送信時に拡張 |
| `protocols.grpc.tls.cert_file` | `str` | 任意 | - | TLS 証明書 | 本番環境向け |
| `protocols.grpc.tls.key_file` | `str` | 任意 | - | TLS 秘密鍵 | 本番環境向け |
| `protocols.http.endpoint` | `str` | 任意 | `0.0.0.0:4318` | HTTP 受付アドレス | - |
| `protocols.http.cors.allowed_origins` | `list[str]` | 任意 | `[]` | CORS 許可オリジン | ブラウザ SDK 直送時のみ |

パラメータ例:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
```

### `batch` processor

telemetry をキューに溜めてバッチで下流に流す processor。
ネットワーク往復回数を減らし exporter 側の負荷を平準化する。
本番運用ではほぼ全パイプラインに入れる標準構成。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `timeout` | `str` | 任意 | `200ms` | フラッシュ間隔 | 5s 程度まで伸ばして OK |
| `send_batch_size` | `int` | 任意 | `8192` | 送信トリガとなるバッチサイズ | この件数に達したら即送信 |
| `send_batch_max_size` | `int` | 任意 | `0`（無制限） | 1 送信の上限件数 | 分割送信の閾値 |

パラメータ例:

```yaml
processors:
  batch:
    send_batch_size: 1024
    timeout: 5s
```

### `attributes` processor

Log / Span record の attribute を追加・更新・削除する processor。
Loki exporter に「Loki ラベルへ昇格させたい attribute キーの一覧」を教える用途にも使う（`loki.attribute.labels` の挿入）。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `actions` | `list` | 必須 | - | attribute 操作の配列 | 子フィールドは下の行で展開 |
| `actions[].action` | `'insert' or 'update' or 'upsert' or 'delete' or 'hash' or 'extract'` | 必須 | - | 操作種別 | insert=既存無しのみ / upsert=常に上書き |
| `actions[].key` | `str` | 必須 | - | 操作対象キー | - |
| `actions[].value` | `str` | 任意 | - | 設定値（insert / update / upsert 時） | `from_attribute` と排他 |
| `actions[].from_attribute` | `str` | 任意 | - | 別 attribute からの値コピー | `value` と排他 |
| `actions[].pattern` | `str` | 任意 | - | 正規表現（extract 時） | 名前付きキャプチャで抽出 |

パラメータ例:

```yaml
processors:
  attributes:
    actions:
      - action: insert
        key: loki.attribute.labels
        value: level,severity
```

### `resource` processor

Resource attribute（`service.name` / `host.name` などのプロセス識別属性）を追加・更新・削除する processor。
インターフェースは [`attributes`](#attributes-processor) と同型で、`actions` 配列に同じ形の要素を並べる。
Loki 側にラベル昇格対象を教える `loki.resource.labels` の挿入もこちらで行う。

パラメータ例:

```yaml
processors:
  resource:
    attributes:
      - action: insert
        key: loki.resource.labels
        value: service.name,service.namespace,host.name
```

### `memory_limiter` processor

Collector プロセスのメモリ使用量を監視し、閾値超過時に新規データを拒否する processor。
OOM で Collector 自身が落ちる前に自己防衛でバックプレッシャをかける。
パイプラインの先頭付近（`[memory_limiter, ...]`）に置くのが定石。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `check_interval` | `str` | 必須 | - | メモリチェック間隔 | 1s 推奨 |
| `limit_mib` | `int` | 任意 | - | ハードリミット (MiB) | `limit_percentage` と排他 |
| `spike_limit_mib` | `int` | 任意 | `limit_mib * 0.2` | スパイク許容量 (MiB) | ソフトリミットとの差分 |
| `limit_percentage` | `int` | 任意 | - | コンテナメモリ上限に対する百分率 | `limit_mib` と排他 |
| `spike_limit_percentage` | `int` | 任意 | - | スパイク許容の百分率 | `spike_limit_mib` と排他 |

パラメータ例:

```yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
```

### `loki` exporter

Log を Grafana Loki の `/loki/api/v1/push` に転送する exporter（contrib ディストリビューション同梱）。
既定では OTLP の Resource / Log record attribute は Loki 側で構造化メタデータに落ち、Stream Selector `{...}` のインデックスラベルには昇格しない。
昇格したい attribute は `resource` / `attributes` processor で `loki.resource.labels` / `loki.attribute.labels` を挿入して指定する（詳細は [OTLP から Loki へのラベル昇格](#otlp-から-loki-へのラベル昇格)）。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `endpoint` | `str` | 必須 | - | Loki の push エンドポイント | 例: `http://loki:3100/loki/api/v1/push` |
| `headers` | `dict[str, str]` | 任意 | `{}` | 送信ヘッダ | マルチテナント時に `X-Scope-OrgID` |
| `tls.insecure` | `bool` | 任意 | `false` | TLS 無効化 | 同一 Compose 内は `true` |
| `sending_queue.enabled` | `bool` | 任意 | `true` | 送信キュー | 一時断からのバッファ回復 |
| `sending_queue.queue_size` | `int` | 任意 | `1000` | キュー最大件数 | - |
| `retry_on_failure.enabled` | `bool` | 任意 | `true` | リトライ有効化 | 4xx はリトライしない |
| `retry_on_failure.initial_interval` | `str` | 任意 | `5s` | 初回リトライ間隔 | 指数バックオフ |

パラメータ例:

```yaml
exporters:
  loki:
    endpoint: http://loki:3100/loki/api/v1/push
```

### `otlp` exporter

OTLP over gRPC で他の Collector / Tempo / OTLP 受信対応バックエンドに転送する exporter。
Collector を「エッジ集約 → 中央集約」の 2 段構成にする場合、上流 Collector の出口として使う。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `endpoint` | `str` | 必須 | - | 送信先 gRPC エンドポイント | 例: `tempo:4317` |
| `tls.insecure` | `bool` | 任意 | `false` | TLS 無効化 | ローカル間は `true` |
| `headers` | `dict[str, str]` | 任意 | `{}` | 送信ヘッダ | 認証用 |
| `compression` | `'none' or 'gzip' or 'zstd' or 'snappy'` | 任意 | `gzip` | 送信圧縮 | ネットワーク帯域と CPU のトレードオフ |
| `sending_queue.enabled` | `bool` | 任意 | `true` | 送信キュー | - |
| `retry_on_failure.enabled` | `bool` | 任意 | `true` | リトライ有効化 | - |

パラメータ例:

```yaml
exporters:
  otlp:
    endpoint: tempo:4317
    tls:
      insecure: true
```

### `debug` exporter

受信した telemetry を stdout に整形出力してから破棄する exporter。
開発時の疎通確認や、正式 exporter を追加するまでの「捨て先」として使う。
`verbosity` で出力量を切り替える。

#### パラメータ

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `verbosity` | `'basic' or 'normal' or 'detailed'` | 任意 | `basic` | 出力の詳細度 | `detailed` は 1 レコードずつ全内容を出力 |
| `sampling_initial` | `int` | 任意 | `2` | サンプル出力の初回件数 | ログ膨張を抑制 |
| `sampling_thereafter` | `int` | 任意 | `500` | 以降のサンプル間隔 | N 件に 1 件出力 |

パラメータ例:

```yaml
exporters:
  debug:
    verbosity: basic
```

### OTLP から Loki へのラベル昇格

`loki` exporter は既定で OTLP の Resource attribute（`service.name` 等）も Log record attribute（`level` 等）も Loki の「構造化メタデータ」側に格納する。
構造化メタデータは `| json` パース後に参照はできるが、Stream Selector `{...}` のインデックスには乗らないので事前フィルタが効かない。
インデックス対象の Loki ラベルとして扱いたい attribute は、`resource` / `attributes` processor で以下の特殊 attribute を挿入し、昇格したいキーをカンマ区切りで列挙する。

| 特殊 attribute | 昇格対象 | 挿入 processor | 補足 |
| --- | --- | --- | --- |
| `loki.resource.labels` | Resource attribute | `resource` | `service.name` / `service.namespace` / `host.name` 等 |
| `loki.attribute.labels` | Log record attribute | `attributes` | `level` / `severity` 等 |

パラメータ例:

```yaml
processors:
  resource:
    attributes:
      - action: insert
        key: loki.resource.labels
        value: service.name,service.namespace,host.name
  attributes:
    actions:
      - action: insert
        key: loki.attribute.labels
        value: level,severity

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [resource, attributes, batch]
      exporters: [loki]
```

- 昇格するラベルはカーディナリティの低い（値の種類が少ない）キーに限定する（`issue_number` のような高カーディナリティ値をラベルに昇格するとインデックスが肥大化する）
- 未指定の attribute は構造化メタデータ側に格納され、Stream Selector でのフィルタからは外れる

### `GET /`

`health_check` extension が公開するヘルスチェックエンドポイント。
Compose の `healthcheck` や依存起動待ちに使う。

#### パラメータ

なし。

パラメータ例:

```bash
curl http://localhost:13133/
```

#### 戻り値

| HTTP ステータス | 説明 | 補足 |
| --- | --- | --- |
| `200 OK` | Collector 正常起動 | ボディは `{"status":"Server available"}` |
| `503 Service Unavailable` | 起動中 or 停止中 | 起動直後・シャットダウン中 |

### `GET /debug/pprof/`

`pprof` extension が公開する Go 標準の pprof プロファイル取得エンドポイント。
CPU / heap / goroutine の解析に使う。

#### パラメータ

Path 末尾でプロファイル種別を切り替える:

| パス | 説明 | 補足 |
| --- | --- | --- |
| `/debug/pprof/` | プロファイル一覧 (HTML) | ブラウザで開くとリンク一覧 |
| `/debug/pprof/heap` | ヒープ使用量スナップショット | `go tool pprof` で読み込む |
| `/debug/pprof/profile?seconds=30` | 30 秒間の CPU プロファイル | サンプリング時間指定 |
| `/debug/pprof/goroutine` | goroutine スタック | デッドロック解析 |

パラメータ例:

```bash
curl -o cpu.pprof "http://localhost:1777/debug/pprof/profile?seconds=30"
go tool pprof cpu.pprof
```

#### 戻り値

| HTTP ステータス | 説明 | 補足 |
| --- | --- | --- |
| `200 OK` | プロファイルバイナリ（pprof 形式） | `go tool pprof` で解析 |
