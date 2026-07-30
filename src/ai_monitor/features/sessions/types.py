"""セッション状態のデータモデル。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


@dataclass(slots=True, kw_only=True)
class AgentSession:
    """起動中 tmux セッション 1 本の状態。"""

    session_name: str
    project: str
    agent_name: str
    primary_number: int
    watch_numbers: list[int] = field(default_factory=list)
    last_seen_at: str = field(default_factory=_now_iso)
    # ユーザー確認ゲートを通知済みの番号（開いたままのゲートを毎周期送らないために持つ）
    notified_gates: list[int] = field(default_factory=list)
