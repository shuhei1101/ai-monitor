"""OTel バックエンド動作確認用の Traces / Metrics / Logs 送信スクリプト."""

from __future__ import annotations

import logging
import os
import random
import sys
from datetime import datetime, timezone

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Meter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

LOGGER_NAME = "ai-monitor-poc"
AGENTS = (
    "single-scenario-writer",
    "epic-conductor",
    "story-conductor",
)


def _endpoint() -> str:
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


def _service_name() -> str:
    return os.environ.get("OTEL_SERVICE_NAME", "ai-monitor-poc")


def _insecure() -> bool:
    return os.environ.get("OTEL_INSECURE", "true").lower() == "true"


def setup_traces(resource: Resource) -> None:
    """TracerProvider をグローバルに登録する."""
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=_endpoint(), insecure=_insecure())
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


def setup_metrics(resource: Resource) -> Meter:
    """MeterProvider をグローバルに登録して Meter を返す."""
    exporter = OTLPMetricExporter(endpoint=_endpoint(), insecure=_insecure())
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return metrics.get_meter(LOGGER_NAME)


def setup_logs(resource: Resource) -> logging.Logger:
    """LoggerProvider をグローバルに登録して標準 logging と接続する."""
    provider = LoggerProvider(resource=resource)
    exporter = OTLPLogExporter(endpoint=_endpoint(), insecure=_insecure())
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)
    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


def emit_traces() -> None:
    """親子 2 段の Span を発行する."""
    tracer = trace.get_tracer(LOGGER_NAME)
    with tracer.start_as_current_span(
        "polling_iteration",
        attributes={"project": "sandbox"},
    ):
        with tracer.start_as_current_span(
            "handle_event",
            attributes={
                "issue.number": 123,
                "agent": "single-scenario-writer",
            },
        ):
            pass


def emit_metrics(meter: Meter) -> None:
    """Counter と Histogram をそれぞれ 3 回発行する."""
    counter = meter.create_counter(
        "agent.session.started",
        unit="1",
        description="起動したエージェントセッション数",
    )
    histogram = meter.create_histogram(
        "agent.turn.duration",
        unit="s",
        description="1 ターンの処理時間",
    )
    for agent in AGENTS:
        counter.add(1, {"agent": agent})
        histogram.record(random.uniform(0.5, 30.0), {"agent": agent})


def emit_logs(logger: logging.Logger) -> None:
    """info / warning / error を 1 回ずつ発行する."""
    logger.info("polling started", extra={"project": "sandbox"})
    logger.warning("assignee not set", extra={"issue.number": 123})
    logger.error("agent session timeout", extra={"agent": "single-scenario-writer"})


def main() -> int:
    """Traces / Metrics / Logs を送信して即時フラッシュする."""
    resource = Resource.create(
        {
            "service.name": _service_name(),
            "service.namespace": "ai-monitor",
            "deployment.environment": "poc",
        }
    )

    print(f"endpoint     : {_endpoint()}")
    print(f"service.name : {_service_name()}")
    print(f"started_at   : {datetime.now(timezone.utc).isoformat()}")

    setup_traces(resource)
    meter = setup_metrics(resource)
    logger = setup_logs(resource)

    emit_traces()
    emit_metrics(meter)
    emit_logs(logger)

    tracer_provider = trace.get_tracer_provider()
    meter_provider = metrics.get_meter_provider()
    from opentelemetry._logs import get_logger_provider

    logger_provider = get_logger_provider()

    if isinstance(tracer_provider, TracerProvider):
        tracer_provider.force_flush()
        tracer_provider.shutdown()
    if isinstance(meter_provider, MeterProvider):
        meter_provider.force_flush()
        meter_provider.shutdown()
    if isinstance(logger_provider, LoggerProvider):
        logger_provider.force_flush()
        logger_provider.shutdown()

    print("送信完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
