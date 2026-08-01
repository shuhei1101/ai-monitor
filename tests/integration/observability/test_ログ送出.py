"""「ログ送出」の結合テスト。"""
from __future__ import annotations

import logging

from opentelemetry._logs import get_logger_provider

from ai_monitor.observability import otel

MESSAGE = "ポーリングを開始します: project=sandbox"


def _find(records, body: str):
    """送出済みレコードから本文が一致する 1 件を取り出す。"""
    return next(record for record in records if record.log_record.body == body)


def test_normal(otel_stub, capsys):
    """初期化後の logging 出力が共通属性付きで送出される（正常系）。"""
    # 準備
    otel.configure("monitor")
    # 実行
    logging.getLogger("ai_monitor.polling").info("ポーリングを開始します: project=%s", "sandbox")
    get_logger_provider().force_flush()
    # 検証: 既定ではコンソールに出さない
    assert MESSAGE not in capsys.readouterr().err
    record = _find(otel_stub.log_exporters[0].records, MESSAGE)
    assert record.log_record.severity_text == "INFO"
    assert record.resource.attributes["service.name"] == "monitor"
    assert record.resource.attributes["service.namespace"] == "ai-monitor"
    assert record.resource.attributes["deployment.environment"] == "dev"


def test_normal_when_console_enabled(otel_stub, monkeypatch, capsys):
    """コンソール出力の設定時に標準エラー出力と OTel の両方へ出る（正常系）。"""
    # 準備
    monkeypatch.setenv("AI_MONITOR_OTEL_CONSOLE_LOG_LEVEL", "WARNING")
    otel.configure("monitor")
    logger = logging.getLogger("ai_monitor.polling")
    # 実行
    logger.warning(MESSAGE)
    logger.info("設定レベル未満のログ")
    get_logger_provider().force_flush()
    # 検証
    err = capsys.readouterr().err
    assert MESSAGE in err
    # 設定したレベル未満はコンソールに出さない（OTel には従来どおり送る）
    assert "設定レベル未満のログ" not in err
    records = otel_stub.log_exporters[0].records
    assert _find(records, MESSAGE) is not None
    assert _find(records, "設定レベル未満のログ") is not None


def test_normal_when_process_exit(otel_stub):
    """停止処理でバッファ済みレコードが送出される（正常系）。"""
    # 準備: フラッシュせずにバッファへ積む
    otel.configure("monitor")
    logging.getLogger("ai_monitor.polling").info(MESSAGE)
    exporter = otel_stub.log_exporters[0]
    # 実行
    otel.shutdown()
    # 検証
    assert _find(exporter.records, MESSAGE) is not None
    assert exporter.shutdown_called is True


def test_error_when_collector_down(otel_stub):
    """送出失敗が呼び出し側に伝播しない（異常系）。"""
    # 準備: 送出時に例外を投げる状態にする
    otel.configure("monitor")
    exporter = otel_stub.log_exporters[0]
    exporter.fail = True
    # 実行・検証: 例外が伝播しない（後続の検証行に到達する）
    logging.getLogger("ai_monitor.polling").info(MESSAGE)
    get_logger_provider().force_flush()
    assert exporter.export_calls >= 1
    assert exporter.records == []
