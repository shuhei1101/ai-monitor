"""観測基盤（OpenTelemetry）の初期化。"""
from __future__ import annotations

from observability.otel import configure, shutdown

__all__ = ["configure", "shutdown"]
