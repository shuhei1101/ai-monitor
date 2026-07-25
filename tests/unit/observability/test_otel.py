"""`src/ai_monitor/observability/otel.py` の単体テスト。"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.trace import TracerProvider

from observability import otel
from observability.settings import ObservabilitySettings


class _FakeProcessor:
    """バッチ Processor のスタブ（送出スレッドを起こさない）。"""

    def __init__(self, exporter=None, **kwargs):
        self.exporter = exporter

    def shutdown(self):
        return None

    def force_flush(self, timeout_millis: float = 30_000) -> bool:
        return True


class _FakeMetricReader(MetricReader):
    """MetricReader のスタブ（定期送出スレッドを起こさない）。"""

    def __init__(self, exporter=None, **kwargs):
        super().__init__()
        self.exporter = exporter

    def _receive_metrics(self, metrics_data, timeout_millis: float = 10_000, **kwargs) -> None:
        return None

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        return None


@pytest.fixture(autouse=True)
def _stub_pipeline(monkeypatch, otel_stub):
    """Provider に登録する Processor / Reader をスタブに差し替える。"""
    monkeypatch.setattr(otel, "BatchLogRecordProcessor", _FakeProcessor)
    monkeypatch.setattr(otel, "BatchSpanProcessor", _FakeProcessor)
    monkeypatch.setattr(otel, "PeriodicExportingMetricReader", _FakeMetricReader)


# =========================
# configure
# =========================


def test_configure(monkeypatch, otel_stub):
    """3 Provider 起動 + root ハンドラ追加 + atexit 登録（正常系）。"""
    # 準備: グローバル登録の setter を記録用に差し替える
    set_logger, set_tracer, set_meter = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(otel, "set_logger_provider", set_logger)
    monkeypatch.setattr(otel.trace, "set_tracer_provider", set_tracer)
    monkeypatch.setattr(otel.metrics, "set_meter_provider", set_meter)
    root = logging.getLogger()
    handler_count = len(root.handlers)
    # 実行
    otel.configure("monitor")
    # 検証
    assert isinstance(set_logger.call_args.args[0], LoggerProvider)
    assert isinstance(set_tracer.call_args.args[0], TracerProvider)
    assert isinstance(set_meter.call_args.args[0], MeterProvider)
    assert len(root.handlers) == handler_count + 1
    assert isinstance(root.handlers[-1], LoggingHandler)
    assert otel.shutdown in otel_stub.atexit_calls


def test_configure_when_reads_env(monkeypatch, otel_stub):
    """設定を環境変数から読む（正常系）。"""
    # 準備
    monkeypatch.setenv("OTEL_OTLP_ENDPOINT", "http://collector:4317")
    monkeypatch.setenv("OTEL_DEPLOYMENT_ENVIRONMENT", "prod")
    # 実行
    otel.configure("monitor")
    # 検証
    assert otel_stub.log_exporters[0].kwargs["endpoint"] == "http://collector:4317"
    assert otel._logger_provider.resource.attributes["deployment.environment"] == "prod"


# =========================
# shutdown
# =========================


def test_shutdown(monkeypatch, otel_stub):
    """3 Provider に対する flush + shutdown（正常系）。"""
    # 準備: 3 Provider をスタブに差し替えて初期化する
    providers = []

    def _provider(*args, **kwargs):
        provider = MagicMock()
        providers.append(provider)
        return provider

    monkeypatch.setattr(otel, "LoggerProvider", _provider)
    monkeypatch.setattr(otel, "TracerProvider", _provider)
    monkeypatch.setattr(otel, "MeterProvider", _provider)
    otel.configure("monitor")
    # 実行
    otel.shutdown()
    # 検証
    assert len(providers) == 3
    for provider in providers:
        provider.force_flush.assert_called_once_with()
        provider.shutdown.assert_called_once_with()


def test_shutdown_when_uninitialized(otel_stub):
    """Provider 未初期化でも例外を投げない（正常系）。"""
    # 実行・検証: 初期化前に呼んでも例外なく戻る
    otel.shutdown()


# =========================
# _build_resource
# =========================


def test_build_resource():
    """3 属性を持つ Resource 生成（正常系）。"""
    # 準備
    settings = ObservabilitySettings(service_namespace="ai-monitor", deployment_environment="prod")
    # 実行
    resource = otel._build_resource("github-mcp", settings)
    # 検証
    assert resource.attributes["service.name"] == "github-mcp"
    assert resource.attributes["service.namespace"] == "ai-monitor"
    assert resource.attributes["deployment.environment"] == "prod"


# =========================
# _configure_logs
# =========================


def test_configure_logs(monkeypatch, otel_stub):
    """LoggerProvider 起動 + root ハンドラ追加（正常系）。"""
    # 準備
    set_logger = MagicMock()
    monkeypatch.setattr(otel, "set_logger_provider", set_logger)
    settings = ObservabilitySettings()
    resource = otel._build_resource("monitor", settings)
    root = logging.getLogger()
    handler_count = len(root.handlers)
    # 実行
    otel._configure_logs(resource, settings)
    # 検証
    assert isinstance(set_logger.call_args.args[0], LoggerProvider)
    assert len(root.handlers) == handler_count + 1
    assert isinstance(root.handlers[-1], LoggingHandler)
    assert root.level == logging.INFO


def test_configure_logs_when_endpoint_overridden(monkeypatch, otel_stub):
    """Exporter が設定の endpoint を受ける（正常系）。"""
    # 準備
    monkeypatch.setattr(otel, "set_logger_provider", MagicMock())
    settings = ObservabilitySettings(otlp_endpoint="http://collector:4317")
    resource = otel._build_resource("monitor", settings)
    # 実行
    otel._configure_logs(resource, settings)
    # 検証
    assert otel_stub.log_exporters[0].kwargs["endpoint"] == "http://collector:4317"


# =========================
# _configure_traces
# =========================


def test_configure_traces(monkeypatch, otel_stub):
    """TracerProvider 起動（正常系）。"""
    # 準備
    set_tracer = MagicMock()
    monkeypatch.setattr(otel.trace, "set_tracer_provider", set_tracer)
    settings = ObservabilitySettings()
    resource = otel._build_resource("monitor", settings)
    # 実行
    otel._configure_traces(resource, settings)
    # 検証
    assert isinstance(set_tracer.call_args.args[0], TracerProvider)


def test_configure_traces_when_endpoint_overridden(monkeypatch, otel_stub):
    """Exporter が設定の endpoint を受ける（正常系）。"""
    # 準備
    monkeypatch.setattr(otel.trace, "set_tracer_provider", MagicMock())
    settings = ObservabilitySettings(otlp_endpoint="http://collector:4317")
    resource = otel._build_resource("monitor", settings)
    # 実行
    otel._configure_traces(resource, settings)
    # 検証
    assert otel_stub.span_exporters[0].kwargs["endpoint"] == "http://collector:4317"


# =========================
# _configure_metrics
# =========================


def test_configure_metrics(monkeypatch, otel_stub):
    """MeterProvider 起動（正常系）。"""
    # 準備
    set_meter = MagicMock()
    monkeypatch.setattr(otel.metrics, "set_meter_provider", set_meter)
    settings = ObservabilitySettings()
    resource = otel._build_resource("monitor", settings)
    # 実行
    otel._configure_metrics(resource, settings)
    # 検証
    assert isinstance(set_meter.call_args.args[0], MeterProvider)


def test_configure_metrics_when_endpoint_overridden(monkeypatch, otel_stub):
    """Exporter が設定の endpoint を受ける（正常系）。"""
    # 準備
    monkeypatch.setattr(otel.metrics, "set_meter_provider", MagicMock())
    settings = ObservabilitySettings(otlp_endpoint="http://collector:4317")
    resource = otel._build_resource("monitor", settings)
    # 実行
    otel._configure_metrics(resource, settings)
    # 検証
    assert otel_stub.metric_exporters[0].kwargs["endpoint"] == "http://collector:4317"
