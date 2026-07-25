"""観測基盤（OpenTelemetry）の初期化。"""
from __future__ import annotations

from ai_monitor.observability.otel import configure, shutdown

__all__ = ["configure", "shutdown"]
