"""観測基盤の設定（OTLP 送信先 / 環境名）。"""
from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilitySettings(BaseSettings):
    """`AI_MONITOR_OTEL_*` 環境変数を型安全に読む観測設定。"""

    model_config = SettingsConfigDict(env_prefix="AI_MONITOR_OTEL_", extra="ignore")

    otlp_endpoint: str = "http://localhost:4317"
    otlp_insecure: bool = True
    deployment_environment: Literal["dev", "staging", "prod"] = "dev"
    service_namespace: str = "ai-monitor"
    # 標準エラー出力へ出すレベル（None なら出さない。tmux でプロセスの画面を見るときに使う）
    console_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
