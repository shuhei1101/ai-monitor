# SigNoz PoC

OpenTelemetry バックエンド候補として SigNoz を評価するための最小構成。

## 方式

**方式 A（公式 clone 利用）** を採用。

SigNoz は Query Service / Frontend / OTel Collector / ClickHouse / Zookeeper / Alertmanager など 8 コンテナ前後で構成され、専用の設定ファイル群（otel-collector-config・clickhouse 初期化スクリプト等）も抱えるため、独自に compose を書き起こすと上流との drift 保守が発生する。
PoC は評価が目的なので、公式リポジトリを clone してそのまま起動する。

## 前提

- Docker Desktop（WSL2 バックエンド有効）または Docker Engine + docker compose v2
- git

## 他 PoC との衝突

同時に起動しないこと（同じポートを奪い合う）。

| ポート | 用途 | 衝突する PoC |
| --- | --- | --- |
| 4317 | OTLP gRPC | jaeger / loki |
| 4318 | OTLP HTTP | jaeger / loki |

起動前に他 PoC が動いていないか確認する。

```bash
docker ps --filter "publish=4317" --filter "publish=4318"
```

## 起動手順

このディレクトリ（`poc/otel-backends/signoz/`）を作業ディレクトリとする。

### 1. 公式リポジトリを clone

```bash
git clone --depth 1 https://github.com/SigNoz/signoz.git
```

`signoz/` は `.gitignore` で除外済み。

### 2. 起動

```bash
cd signoz/deploy/docker
docker compose -p signoz-poc up -d
```

`-p signoz-poc` で Compose のプロジェクト名を上書きし、コンテナ名を `signoz-poc-*` プレフィックスにする。
リスタートポリシーは公式 compose 側で `on-failure` / `always` が設定されている（PoC 用途では十分）。

### 3. 起動確認

```bash
docker compose -p signoz-poc ps
```

全サービスが `running` / `healthy` になるまで初回は 2〜3 分かかる（ClickHouse の初期化のため）。

## アクセス

### UI

- URL: http://localhost:3301
- 初回アクセス時にアカウント作成画面が出るので、任意のメールアドレス / パスワードで登録する
  - デフォルトの `admin@signoz.io / admin` は SigNoz 側で用意されていない（自己ホスト版は初回セットアップで管理者を作る方式）
  - PoC 用途では `poc@example.com / poc-password` 等でよい

### OTLP 送信エンドポイント

アプリケーション側の OTel SDK / Collector から SigNoz に送るときは以下を指定する。

| プロトコル | エンドポイント |
| --- | --- |
| OTLP gRPC | `localhost:4317` |
| OTLP HTTP | `http://localhost:4318` |

例（環境変数）:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

## 停止

```bash
cd signoz/deploy/docker
docker compose -p signoz-poc down
```

データも消したい場合:

```bash
docker compose -p signoz-poc down -v
```

## 完全削除（PoC 終了時）

```bash
cd signoz/deploy/docker
docker compose -p signoz-poc down -v
cd /mnt/c/Users/shuhe/repo/ai-monitor/poc/otel-backends/signoz
rm -rf signoz/
```
