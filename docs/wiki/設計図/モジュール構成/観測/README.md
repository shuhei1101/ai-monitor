---
template_version: 1.4.0
---

# モジュール構成: 観測

`観測` サブシステムの索引ページ。
モニター / MCP サーバー 常駐プロセスから OpenTelemetry Collector へ telemetry（現状は Log のみ）を送出するための SDK 初期化コードを扱う。

## 目次

| ページ | 概要 |
| --- | --- |
| [OTel初期化](./OTel初期化.py.md) | OpenTelemetry SDK（Log / Trace / Metric Provider）を起動時に 1 回配線するモジュール |
