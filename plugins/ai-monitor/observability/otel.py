"""OpenTelemetry SDK の Provider 配線と停止。"""
from __future__ import annotations

import atexit
import logging

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from observability.settings import ObservabilitySettings

# 停止時に flush する対象。configure を呼ぶまでは未生成
_logger_provider: LoggerProvider | None = None
_tracer_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None


def configure(service_name: str) -> None:
    """3 Provider を配線し、標準 logging を OTel Collector へ橋渡しする。"""
    settings = ObservabilitySettings()
    resource = _build_resource(service_name, settings)
    _configure_logs(resource, settings)
    _configure_traces(resource, settings)
    _configure_metrics(resource, settings)
    atexit.register(shutdown)


def shutdown() -> None:
    """配線済みの Provider をフラッシュして停止する。"""
    for provider in (_logger_provider, _tracer_provider, _meter_provider):
        # 未生成の Provider は対象外（configure 前のプロセス終了を想定）
        if provider is None:
            continue
        provider.force_flush()
        provider.shutdown()


def _build_resource(service_name: str, settings: ObservabilitySettings) -> Resource:
    """telemetry に共通で載せる Resource を作る。"""
    return Resource.create(
        {
            "service.name": service_name,
            "service.namespace": settings.service_namespace,
            "deployment.environment": settings.deployment_environment,
        }
    )


def _configure_logs(resource: Resource, settings: ObservabilitySettings) -> None:
    """LoggerProvider を配線し、root logger にハンドラを追加する。"""
    global _logger_provider
    exporter = OTLPLogExporter(endpoint=settings.otlp_endpoint, insecure=settings.otlp_insecure)
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)
    _logger_provider = provider
    root = logging.getLogger()
    root.addHandler(LoggingHandler(level=logging.INFO, logger_provider=provider))
    # root の既定レベル（WARNING）のままでは INFO ログがレコード化されない
    root.setLevel(logging.INFO)


def _configure_traces(resource: Resource, settings: ObservabilitySettings) -> None:
    """TracerProvider を配線する。"""
    global _tracer_provider
    exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=settings.otlp_insecure)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer_provider = provider


def _configure_metrics(resource: Resource, settings: ObservabilitySettings) -> None:
    """MeterProvider を配線する。"""
    global _meter_provider
    exporter = OTLPMetricExporter(endpoint=settings.otlp_endpoint, insecure=settings.otlp_insecure)
    reader = PeriodicExportingMetricReader(exporter)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    _meter_provider = provider
