"""`src/ai_monitor/features/rate_limit/gate.py` の単体テスト。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_monitor.features.rate_limit.gate import RateLimitGate

NOW = datetime(2026, 7, 29, 1, 0, tzinfo=timezone.utc)
SESSION = "ai-monitor-sandbox-1069-epic-conductor"


@pytest.fixture
def gate() -> RateLimitGate:
    """待機していない関門を返す。"""
    return RateLimitGate()


def test_block(gate):
    """待機の記録を確認する（正常系）。"""
    # 実行
    gate.block(SESSION, NOW + timedelta(minutes=30))
    # 検証: 解除時刻まで待機中で、解除後は対象が取り出せる
    assert gate.is_blocked(NOW) is True
    assert gate.take_resumable(NOW + timedelta(minutes=31)) == [SESSION]


def test_block_when_later_time_given(gate):
    """より遅い時刻の採用を確認する（正常系）。"""
    # 準備
    gate.block(SESSION, NOW + timedelta(minutes=30))
    # 実行
    gate.block("ai-monitor-sandbox-1070-story-conductor", NOW + timedelta(minutes=60))
    # 検証: 遅いほうの時刻が残っている
    assert gate.is_blocked(NOW + timedelta(minutes=45)) is True


def test_block_when_earlier_time_given(gate):
    """より早い時刻の無視を確認する（正常系）。"""
    # 準備
    gate.block(SESSION, NOW + timedelta(minutes=60))
    # 実行
    gate.block("ai-monitor-sandbox-1070-story-conductor", NOW + timedelta(minutes=30))
    # 検証: 記録済みの時刻が残っている
    assert gate.is_blocked(NOW + timedelta(minutes=45)) is True


def test_block_when_duplicate_session(gate):
    """同一セッションの重複を確認する（正常系）。"""
    # 準備
    gate.block(SESSION, NOW + timedelta(minutes=30))
    # 実行
    gate.block(SESSION, NOW + timedelta(minutes=30))
    # 検証: 再開待ちが重複していない
    assert gate.take_resumable(NOW + timedelta(minutes=31)) == [SESSION]


def test_is_blocked(gate):
    """待機中の判定を確認する（正常系）。"""
    # 準備
    gate.block(SESSION, NOW + timedelta(minutes=30))
    # 実行・検証
    assert gate.is_blocked(NOW) is True


def test_is_blocked_when_passed(gate):
    """解除済みの判定を確認する（正常系）。"""
    # 準備
    gate.block(SESSION, NOW + timedelta(minutes=30))
    # 実行・検証
    assert gate.is_blocked(NOW + timedelta(minutes=31)) is False


def test_is_blocked_when_not_blocked(gate):
    """未待機の判定を確認する（正常系）。"""
    # 実行・検証
    assert gate.is_blocked(NOW) is False


def test_take_resumable(gate):
    """解除後の取り出しを確認する（正常系）。"""
    # 準備
    other = "ai-monitor-sandbox-1070-story-conductor"
    gate.block(SESSION, NOW + timedelta(minutes=30))
    gate.block(other, NOW + timedelta(minutes=30))
    # 実行
    resumable = gate.take_resumable(NOW + timedelta(minutes=31))
    # 検証: 2 件返り、待機状態が消えている
    assert resumable == [SESSION, other]
    assert gate.is_blocked(NOW) is False


def test_take_resumable_when_blocked(gate):
    """待機中は取り出さないことを確認する（正常系）。"""
    # 準備
    gate.block(SESSION, NOW + timedelta(minutes=30))
    # 実行
    resumable = gate.take_resumable(NOW)
    # 検証: 空リストで待機状態は残っている
    assert resumable == []
    assert gate.is_blocked(NOW) is True


def test_take_resumable_when_twice(gate):
    """二度目の取り出しが空になることを確認する（正常系）。"""
    # 準備
    gate.block(SESSION, NOW + timedelta(minutes=30))
    gate.take_resumable(NOW + timedelta(minutes=31))
    # 実行
    resumable = gate.take_resumable(NOW + timedelta(minutes=32))
    # 検証: 同じ対象へ二重送信しない
    assert resumable == []
