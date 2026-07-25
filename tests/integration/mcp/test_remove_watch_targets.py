"""「監視対象除去」の結合テスト。"""
from __future__ import annotations

import pytest

import ai_monitor.mcp.server as server
from ai_monitor.features.sessions.state_store import load_sessions
from ai_monitor.mcp.models import MonitorAck


def test_normal(api, mon_registry, session_factory, tmp_state_path):
    """プロジェクト解決 → セッション検索 → 監視面除去の一連を確認する（正常系）。"""
    # 準備
    session_factory("architect", 52, watch_numbers=[60, 61])
    # 実行
    res = api.remove_watch_targets("architect", 52, [60])
    # 検証
    assert mon_registry.find("sandbox", "architect", 52).watch_numbers == [61]
    assert load_sessions(tmp_state_path)[0].watch_numbers == [61]
    assert res == MonitorAck(ok=True)


def test_error_when_unknown_session(api, tmp_state_path):
    """台帳に該当セッションがない場合のエラーを確認する（異常系・セッション不明）。"""
    # 実行・検証
    with pytest.raises(server.SessionNotFoundError):
        api.remove_watch_targets("architect", 52, [60])
    assert load_sessions(tmp_state_path) == []
