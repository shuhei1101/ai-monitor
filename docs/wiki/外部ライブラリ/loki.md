---
template_version: 1.0.0
---

# Grafana Loki

Grafana Labs 製のログ集約バックエンド。
ラベル付きストリームとしてログを保存し、LogQL で絞り込み検索する。
Prometheus の設計思想（少数の低カーディナリティ・ラベルをインデックス化し、全文はチャンクに保存）をログに適用したもの。

## 概要

ログの受信・保存・検索を担うサーバ製品。
書き込みは HTTP `POST /loki/api/v1/push`、検索は LogQL（`{label="v"} |= "text"`）で行う。
シングルバイナリ + `filesystem` storage で開発 / PoC 用途に、マイクロサービス + object storage で本番用途に、同じバイナリで両対応する。

## 現在のバージョン情報

| 項目 | 内容 | 補足 |
| --- | --- | --- |
| バージョン | `3.2.1` | 2026-07-24 時点最新 |
| ライセンス | AGPL-3.0 | - |
| 公式 URL | https://github.com/grafana/loki | - |
| 公式ドキュメント | https://grafana.com/docs/loki/latest/ | - |

## インストール手順

Docker Compose で単一バイナリモードとして起動する構成:

```yaml
services:
  loki:
    image: grafana/loki:3.2.1
    container_name: loki
    restart: unless-stopped
    command:
      - "-config.file=/etc/loki/loki-config.yaml"
    volumes:
      - ./loki-config.yaml:/etc/loki/loki-config.yaml:ro
      - loki-data:/loki
    ports:
      - "3100:3100"

volumes:
  loki-data:
```

最小の `loki-config.yaml`:

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  allow_structured_metadata: true
  volume_enabled: true

analytics:
  reporting_enabled: false
```

- 公開ポート `3100` が HTTP（Push / Query）、内部の `9096` が gRPC（コンポーネント間通信）
- 他コンテナからは `http://loki:3100` で参照する
- 単一バイナリ + `filesystem` storage は開発 / PoC 向け構成で、本番は object storage（S3 / GCS 等）+ マイクロサービス配置に切り替える

## API 一覧

バージョン: `3.2.1`

| 種別 | 名前 | 用途 | 補足 |
| --- | --- | --- | --- |
| 設定 | [`loki-config.yaml`](#loki-configyaml) | Loki サーバの起動設定 | filesystem storage の PoC 前提で主要項目のみ |
| 構文 | [`LogQL`](#logql) | ログクエリ言語 | Grafana / HTTP API どちらでも共通 |
| エンドポイント | [`POST /loki/api/v1/push`](#post-lokiapiv1push) | ログ書き込み | OTel Collector が使う |
| エンドポイント | [`GET /loki/api/v1/query_range`](#get-lokiapiv1query_range) | 時間範囲クエリ | LogQL で絞り込み |
| エンドポイント | [`GET /loki/api/v1/labels`](#get-lokiapiv1labels) | 利用可能なラベル名一覧 | UI の候補列挙用 |
| エンドポイント | [`GET /loki/api/v1/label/{name}/values`](#get-lokiapiv1labelnamevalues) | 特定ラベルの取り得る値一覧 | UI の候補列挙用 |
| エンドポイント | [`GET /ready`](#get-ready) | ヘルスチェック | 起動完了判定 |
| 挙動 | [OTLP から Loki へのラベル昇格](#otlp-から-loki-へのラベル昇格) | OTLP attribute の Loki ラベル化 | Collector の attributes プロセッサで指定 |

### `loki-config.yaml`

Loki サーバの起動時に読み込まれる設定ファイル。
`-config.file` オプションでパスを渡す。

#### 設定項目

| パス | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `auth_enabled` | `bool` | 任意 | `true` | マルチテナント認証を有効化 | シングルテナント運用は `false` |
| `server.http_listen_port` | `int` | 任意 | `3100` | HTTP 受付ポート | Push / Query で共通 |
| `server.grpc_listen_port` | `int` | 任意 | `9095` | gRPC 受付ポート | コンポーネント間通信 |
| `server.log_level` | `'debug' or 'info' or 'warn' or 'error'` | 任意 | `info` | Loki 自身のログレベル | - |
| `common.path_prefix` | `str` | 任意 | - | 各種データ配置のルート | filesystem storage では実質必須 |
| `common.storage.filesystem.chunks_directory` | `str` | 任意 | - | チャンク（ログ本体）の保存先 | PoC は `/loki/chunks` |
| `common.storage.filesystem.rules_directory` | `str` | 任意 | - | Ruler ルールの保存先 | PoC は `/loki/rules` |
| `common.replication_factor` | `int` | 任意 | `1` | ログのレプリケーション数 | 単一バイナリは `1` |
| `common.ring.kvstore.store` | `'inmemory' or 'consul' or 'etcd' or 'memberlist'` | 任意 | `consul` | ハッシュリング用 KV ストア | 単一バイナリは `inmemory` |
| `schema_config.configs[].from` | `str` | 必須 | - | このスキーマ設定の有効開始日 | ISO 8601 日付（`2024-01-01`） |
| `schema_config.configs[].store` | `'tsdb' or 'boltdb-shipper'` | 必須 | - | インデックスストア形式 | 3.x 系は `tsdb` 推奨 |
| `schema_config.configs[].object_store` | `'filesystem' or 's3' or 'gcs' or 'azure'` | 必須 | - | チャンク保存先バックエンド | PoC は `filesystem` |
| `schema_config.configs[].schema` | `str` | 必須 | - | スキーマバージョン | 3.x 系は `v13` |
| `schema_config.configs[].index.prefix` | `str` | 必須 | - | インデックスファイル名の接頭辞 | 例: `index_` |
| `schema_config.configs[].index.period` | `str` | 必須 | - | インデックスの回転周期 | `24h` 固定推奨 |
| `limits_config.allow_structured_metadata` | `bool` | 任意 | `false` | 構造化メタデータの受け入れ | OTLP attribute を保持したければ `true` |
| `limits_config.volume_enabled` | `bool` | 任意 | `false` | ラベルボリューム API を有効化 | 使用量統計・カーディナリティ確認用 |
| `limits_config.reject_old_samples` | `bool` | 任意 | `true` | 古すぎるサンプルの拒否 | - |
| `limits_config.reject_old_samples_max_age` | `str` | 任意 | `168h` | 古サンプル判定の閾値 | 7 日 |
| `ruler.alertmanager_url` | `str` | 任意 | - | Alertmanager の URL | アラートルール実行時のみ必要 |
| `analytics.reporting_enabled` | `bool` | 任意 | `true` | 使用状況を Grafana Labs に送信 | オフにする場合は `false` |

パラメータ例:

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  allow_structured_metadata: true
  volume_enabled: true
```

- `limits_config.metric_aggregation_enabled` は Loki 3.2.1 には存在しない（3.3+ で追加）
- 設定に含めるとバリデーションエラーで起動に失敗するため、3.2.1 系では書かない

### `LogQL`

Loki の独自クエリ言語。
`{Log Stream Selector} | {Log Pipeline}` の 2 段構成で、Stream Selector で対象ログを絞り、Pipeline でフィルタ・パース・整形を追加する。

#### 構文

| 構文 | 意味 | 例 |
| --- | --- | --- |
| `{label="value"}` | Stream Selector（完全一致） | `{service_name="ai-monitor"}` |
| `{label=~"regex"}` | Stream Selector（正規表現一致） | `{service_name=~".+"}` |
| `{label!="value"}` | Stream Selector（不一致） | `{service_name!="test"}` |
| `{label!~"regex"}` | Stream Selector（正規表現不一致） | `{service_name!~"^test-.*"}` |
| `\|= "text"` | Line filter（部分文字列一致） | `{...} \|= "error"` |
| `\|~ "regex"` | Line filter（正規表現一致） | `{...} \|~ "level=(error\|warn)"` |
| `!= "text"` | Line filter（部分文字列不一致） | `{...} != "healthcheck"` |
| `!~ "regex"` | Line filter（正規表現不一致） | `{...} !~ "^debug"` |
| `\| json` | JSON パーサ | ログ本体を JSON として解釈し各フィールドをラベル化 |
| `\| json \| field="value"` | JSON パース後の値でフィルタ | `\| json \| level="error"` |
| `\| logfmt` | logfmt パーサ | `key=value key2=value2` 形式を各フィールドに展開 |
| `\| line_format "template"` | 出力行の再整形 | `\| line_format "{{.level}} {{.msg}}"` |
| `\| label_format label="expr"` | ラベルの追加・変換 | `\| label_format app="{{.service_name}}"` |

パラメータ例:

```logql
{service_name="ai-monitor", agent="single-scenario-writer"}
  |= "issue"
  | json
  | issue_number="123"
  | line_format "{{.level}} [{{.agent}}] {{.msg}}"
```

- Stream Selector には最低 1 つ以上の等値マッチ（`=` or `=~"..+"` 相当）が必要
- Line filter は左から順に評価されるため、先頭にヒット率の高いフィルタを置くと高速化する

### `POST /loki/api/v1/push`

ログを書き込むエンドポイント。
OTel Collector の Loki exporter がこのエンドポイントに送信する。

#### パラメータ

Content-Type は `application/json`（他に protobuf / snappy も可）。
リクエストボディは JSON:

| フィールド | 型 | 必須 | 説明 | 補足 |
| --- | --- | --- | --- | --- |
| `streams` | `list` | 必須 | ログストリームの配列 | 子フィールドは下の行で展開 |
| `streams[].stream` | `dict[str, str]` | 必須 | ラベル辞書 | 例: `{"service_name": "ai-monitor"}` |
| `streams[].values` | `list[list[str, str]]` | 必須 | `[timestamp_ns, line]` の配列 | 時刻はナノ秒精度 |
| `streams[].values[][0]` | `str` | 必須 | Unix ナノ秒（10 進文字列） | 例: `"1700000000000000000"` |
| `streams[].values[][1]` | `str` | 必須 | ログ本文 | 任意の文字列 |

パラメータ例:

```bash
curl -X POST http://localhost:3100/loki/api/v1/push \
  -H "Content-Type: application/json" \
  -d '{
    "streams": [
      {
        "stream": { "service_name": "ai-monitor", "level": "info" },
        "values": [
          ["1700000000000000000", "started polling loop"]
        ]
      }
    ]
  }'
```

#### 戻り値

| HTTP ステータス | 説明 | 補足 |
| --- | --- | --- |
| `204 No Content` | 受理成功 | ボディなし |
| `400 Bad Request` | ラベル / 時刻フォーマット不正 | - |
| `429 Too Many Requests` | レート制限超過 | `limits_config` の ingestion rate に到達 |

### `GET /loki/api/v1/query_range`

時間範囲を指定してログを取得する。

#### パラメータ

Query string:

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `query` | `str` | 必須 | - | LogQL クエリ | URL エンコード必須 |
| `start` | `str` | 任意 | 1 時間前 | 開始時刻 | Unix ナノ秒 or RFC3339 |
| `end` | `str` | 任意 | 現在 | 終了時刻 | Unix ナノ秒 or RFC3339 |
| `limit` | `int` | 任意 | `100` | 最大取得件数 | 上限 5000 |
| `direction` | `'forward' or 'backward'` | 任意 | `backward` | 並び順 | `backward`=新しい順 |
| `step` | `str` | 任意 | 自動 | サンプル間隔 | メトリクスクエリ時のみ |

パラメータ例:

```bash
curl -G http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={service_name="ai-monitor"} |= "error"' \
  --data-urlencode 'limit=50' \
  --data-urlencode 'direction=backward'
```

#### 戻り値

| フィールド | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `status` | `str` | `"success"` 固定 | 失敗時は HTTP 4xx / 5xx |
| `data.resultType` | `'streams' or 'matrix' or 'vector'` | 結果タイプ | ログクエリは `streams` |
| `data.result` | `list` | 結果配列 | 子フィールドは下の行で展開 |
| `data.result[].stream` | `dict[str, str]` | ストリームのラベル | - |
| `data.result[].values` | `list[list[str, str]]` | `[timestamp_ns, line]` の配列 | - |
| `data.stats` | `dict` | クエリ統計 | 実行時間・スキャン量など |

戻り値例:

```json
{
  "status": "success",
  "data": {
    "resultType": "streams",
    "result": [
      {
        "stream": { "service_name": "ai-monitor", "level": "error" },
        "values": [
          ["1700000000000000000", "failed to load config"]
        ]
      }
    ],
    "stats": { "summary": { "execTime": 0.012 } }
  }
}
```

### `GET /loki/api/v1/labels`

利用可能なラベル名の一覧を取得する。
UI のフィルタ候補列挙などに使う。

#### パラメータ

Query string:

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `start` | `str` | 任意 | 6 時間前 | 対象時間範囲の開始 | Unix ナノ秒 or RFC3339 |
| `end` | `str` | 任意 | 現在 | 対象時間範囲の終了 | 同上 |

パラメータ例:

```bash
curl http://localhost:3100/loki/api/v1/labels
```

#### 戻り値

| フィールド | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `status` | `str` | `"success"` 固定 | - |
| `data` | `list[str]` | ラベル名の配列 | - |

戻り値例:

```json
{
  "status": "success",
  "data": ["service_name", "agent", "level"]
}
```

### `GET /loki/api/v1/label/{name}/values`

特定ラベルが実際に取り得る値の一覧を取得する。

#### パラメータ

Path + Query:

| パラメータ | 型 | 必須 | 既定 | 説明 | 補足 |
| --- | --- | --- | --- | --- | --- |
| `{name}` | `str` | 必須 | - | 対象ラベル名 | パス部分 |
| `start` | `str` | 任意 | 6 時間前 | 対象時間範囲の開始 | Query |
| `end` | `str` | 任意 | 現在 | 対象時間範囲の終了 | Query |

パラメータ例:

```bash
curl http://localhost:3100/loki/api/v1/label/service_name/values
```

#### 戻り値

| フィールド | 型 | 説明 | 補足 |
| --- | --- | --- | --- |
| `status` | `str` | `"success"` 固定 | - |
| `data` | `list[str]` | ラベル値の配列 | - |

戻り値例:

```json
{
  "status": "success",
  "data": ["ai-monitor", "sandbox"]
}
```

### `GET /ready`

Loki の起動完了を判定するヘルスチェック。
Compose の `healthcheck` や依存起動待ちに使う。

#### パラメータ

なし。

パラメータ例:

```bash
curl http://localhost:3100/ready
```

#### 戻り値

| HTTP ステータス | 説明 | 補足 |
| --- | --- | --- |
| `200 OK` | 準備完了（クエリ / 書き込み受付可能） | ボディは `ready` |
| `503 Service Unavailable` | 準備中 | 起動直後・初期化未完了 |

### OTLP から Loki へのラベル昇格

OTel Collector が Loki exporter で送信するとき、既定では Resource attribute（`service.name` 等）も Log record attribute（`level` 等）も「構造化メタデータ」側に落ち、Loki のインデックス対象ラベルにはならない。
インデックス対象（Stream Selector `{...}` でフィルタできるラベル）にしたい attribute は、Collector の `resource` / `attributes` プロセッサで `loki.resource.labels` / `loki.attribute.labels` という特殊 attribute を挿入し、昇格したいキーをカンマ区切りで列挙する。

| 特殊 attribute | 昇格対象 | 補足 |
| --- | --- | --- |
| `loki.resource.labels` | Resource attribute | `service.name` / `service.namespace` / `host.name` 等 |
| `loki.attribute.labels` | Log record attribute | `level` / `severity` 等 |

パラメータ例（Collector 側の設定断片）:

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
```

- 未指定の attribute は構造化メタデータ側に格納され、LogQL の Stream Selector（`{...}`）ではフィルタできない
- 構造化メタデータは `| json` パース後にフィールドとして参照できるが、事前フィルタが効かないため高頻度クエリのキーには不向き
- 昇格するラベルはカーディナリティが低い（値の種類が少ない）ものに限定する（Prometheus と同じ制約で、`issue_number` のような高カーディナリティ値をラベルに昇格するとインデックスが肥大化する）
