"""設定リロードの DTO と、差し替え可能にしておく依存の関数型。"""
from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from ai_monitor.features.agents.types import Agent
from ai_monitor.shared.settings import Settings


class IgnoredItem(BaseModel):
    """再読込で反映しなかった設定項目 1 件。"""

    item: str = Field(description="反映しなかった設定項目名")
    reason: str = Field(description="反映しない理由")


class ReloadResult(BaseModel):
    """再読込の反映結果。"""

    added: list[str] = Field(default_factory=list, description="追加された監視対象プロジェクト名")
    removed: list[str] = Field(default_factory=list, description="削除された監視対象プロジェクト名")
    ignored: list[IgnoredItem] = Field(
        default_factory=list, description="実行中に変えられないため反映しなかった項目"
    )


type ReadSettings = Callable[[], Settings]
type BuildAgents = Callable[[Settings], list[Agent]]
