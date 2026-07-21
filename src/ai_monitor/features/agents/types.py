"""エージェント定義のデータモデル。"""
from __future__ import annotations

from dataclasses import dataclass

from ai_monitor.shared.types import LabelName


@dataclass(frozen=True, slots=True, kw_only=True)
class Agent:
    """1 エージェントの静的定義。"""

    name: str
    confirm_label: LabelName
    processing_label: LabelName
    model: str
    standalone: bool = False
