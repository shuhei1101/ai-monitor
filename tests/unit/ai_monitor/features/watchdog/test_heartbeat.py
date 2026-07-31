"""`features/watchdog/heartbeat.py` の単体テスト。"""
from __future__ import annotations

from datetime import datetime, timezone

from ai_monitor.features.watchdog.heartbeat import touch_heartbeat


def test_touch_heartbeat(tmp_path):
    """最終周回時刻の書き出しを確認する（正常系）。"""
    # 準備
    path = tmp_path / "nested" / "monitor.heartbeat"
    now = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
    # 実行
    touch_heartbeat(path, now=now)
    # 検証
    assert datetime.fromisoformat(path.read_text(encoding="utf-8")) == now
