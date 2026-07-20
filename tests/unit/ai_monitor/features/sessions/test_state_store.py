"""`src/ai_monitor/features/sessions/state_store.py` の単体テスト。"""
from __future__ import annotations

import ai_monitor.features.sessions.state_store as state_store
from ai_monitor.features.sessions.types import AgentSession


def _session(number: int) -> AgentSession:
    return AgentSession(
        session_name=f"ai-monitor-sandbox-{number}-epic-conductor",
        project="sandbox",
        agent_name="epic-conductor",
        primary_number=number,
        watch_numbers=[number + 10],
        last_seen_at="2026-07-20T00:00:00+09:00",
    )


def test_load_sessions(tmp_state_path):
    """YAML からの復元を確認する（正常系）。"""
    # 準備
    state_store.save_sessions(tmp_state_path, [_session(35), _session(36)])
    # 実行
    sessions = state_store.load_sessions(tmp_state_path)
    # 検証
    assert sessions == [_session(35), _session(36)]


def test_load_sessions_when_file_missing(tmp_state_path):
    """ファイルなしは空リストを確認する（正常系）。"""
    # 実行
    sessions = state_store.load_sessions(tmp_state_path)
    # 検証
    assert sessions == []


def test_save_sessions(tmp_state_path):
    """保存 → 読み込みの往復とアトミック書きを確認する（正常系）。"""
    # 実行
    state_store.save_sessions(tmp_state_path, [_session(35), _session(36)])
    # 検証
    assert state_store.load_sessions(tmp_state_path) == [_session(35), _session(36)]
    leftovers = [p for p in tmp_state_path.parent.iterdir() if p.name != tmp_state_path.name]
    assert leftovers == []
