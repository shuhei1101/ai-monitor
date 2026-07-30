"""レートリミットの待機状態。"""
from __future__ import annotations

import threading
from datetime import datetime


class RateLimitGate:
    """利用上限の待機状態を保持する。"""

    def __init__(self) -> None:
        # HTTP のワーカースレッドとポーリングのスレッドから同時に触られるため全メソッドを直列化する
        self._lock = threading.RLock()
        self._resets_at: datetime | None = None
        self._blocked: list[str] = []

    def block(self, session_name: str, resets_at: datetime) -> None:
        """対象セッションを再開待ちに積み、解除時刻を記録する。"""
        with self._lock:
            # 複数セッションの通知では最も遅い時刻に揃える
            if self._resets_at is None or resets_at > self._resets_at:
                self._resets_at = resets_at
            # 未登録の対象だけを積む（登録済みは無視する冪等操作）
            if session_name not in self._blocked:
                self._blocked.append(session_name)

    def is_blocked(self, now: datetime) -> bool:
        """現在時刻が解除時刻より前かを返す。"""
        with self._lock:
            if self._resets_at is None:
                return False
            return now < self._resets_at

    def take_resumable(self, now: datetime) -> list[str]:
        """解除済みなら再開待ちのセッション名を取り出し、待機状態を消す。"""
        with self._lock:
            if self._resets_at is None or self.is_blocked(now):
                return []
            # 取り出しと同時に状態を消して同じ対象へ二度送らないようにする
            resumable = self._blocked
            self._resets_at = None
            self._blocked = []
            return resumable
