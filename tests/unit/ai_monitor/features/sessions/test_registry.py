"""`src/ai_monitor/features/sessions/registry.py` の単体テスト。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.features.sessions.types import AgentSession


def _session(project="sandbox", agent="epic-conductor", number=35, watch=None) -> AgentSession:
    return AgentSession(
        session_name=f"ai-monitor-{project}-{number}-{agent}",
        project=project,
        agent_name=agent,
        primary_number=number,
        watch_numbers=watch or [],
        last_seen_at="2026-07-20T00:00:00+09:00",
    )


@pytest.fixture
def save_mock(monkeypatch):
    """永続化関数を MagicMock に差し替える。"""
    mock = MagicMock(name="save_sessions")
    monkeypatch.setattr(registry_mod, "save_sessions", mock)
    return mock


@pytest.fixture
def registry(tmp_state_path, save_mock):
    """登録済み 3 件の台帳を作る。"""
    reg = registry_mod.SessionRegistry(tmp_state_path)
    reg.sessions.extend(
        [
            _session(number=35),
            _session(project="other", number=35),
            _session(agent="architect", number=52, watch=[60, 61]),
        ]
    )
    return reg


def test_find(registry):
    """主番号での検索を確認する（正常系）。"""
    # 実行
    session = registry.find("sandbox", "epic-conductor", 35)
    # 検証
    assert session is not None
    assert session.project == "sandbox"
    assert session.primary_number == 35


def test_find_when_watch_number(registry):
    """監視面での検索を確認する（正常系）。"""
    # 実行
    session = registry.find("sandbox", "architect", 60)
    # 検証
    assert session is not None
    assert session.primary_number == 52


def test_find_when_not_registered(tmp_state_path, save_mock):
    """未登録は None を確認する（正常系）。"""
    # 準備
    reg = registry_mod.SessionRegistry(tmp_state_path)
    # 実行
    session = reg.find("sandbox", "epic-conductor", 35)
    # 検証
    assert session is None


def test_register(tmp_state_path, save_mock):
    """追加と永続化を確認する（正常系）。"""
    # 準備
    reg = registry_mod.SessionRegistry(tmp_state_path)
    session = _session()
    # 実行
    reg.register(session)
    # 検証
    assert reg.sessions == [session]
    save_mock.assert_called_once()


def test_touch(registry, save_mock):
    """生存時刻の更新を確認する（正常系）。"""
    # 準備
    save_mock.reset_mock()
    # 実行
    registry.touch("ai-monitor-sandbox-35-epic-conductor")
    # 検証
    session = registry.find("sandbox", "epic-conductor", 35)
    assert session.last_seen_at != "2026-07-20T00:00:00+09:00"
    save_mock.assert_called_once()


def test_add_watch(registry, save_mock):
    """追加と永続化を確認する（正常系）。"""
    # 準備
    save_mock.reset_mock()
    # 実行
    registry.add_watch("sandbox", "epic-conductor", 35, [70, 71])
    # 検証
    assert registry.find("sandbox", "epic-conductor", 35).watch_numbers == [70, 71]
    save_mock.assert_called_once()


def test_add_watch_when_duplicate_number(registry, save_mock):
    """登録済み番号の無視を確認する（正常系）。"""
    # 実行
    registry.add_watch("sandbox", "architect", 52, [60, 62])
    # 検証
    assert registry.find("sandbox", "architect", 52).watch_numbers == [60, 61, 62]


def test_add_watch_when_session_missing(registry, save_mock):
    """セッション不明を確認する（異常系）。"""
    # 準備
    save_mock.reset_mock()
    before = list(registry.sessions)
    # 実行・検証
    with pytest.raises(KeyError):
        registry.add_watch("sandbox", "epic-conductor", 99, [70])
    assert registry.sessions == before


def test_remove_watch(registry, save_mock):
    """除去と永続化を確認する（正常系）。"""
    # 準備
    save_mock.reset_mock()
    # 実行
    registry.remove_watch("sandbox", "architect", 52, [60])
    # 検証
    assert registry.find("sandbox", "architect", 52).watch_numbers == [61]
    save_mock.assert_called_once()


def test_remove_watch_when_number_missing(registry, save_mock):
    """未登録番号の無視を確認する（正常系）。"""
    # 実行
    registry.remove_watch("sandbox", "architect", 52, [99])
    # 検証
    assert registry.find("sandbox", "architect", 52).watch_numbers == [60, 61]


def test_remove(registry, save_mock):
    """1 件除去と永続化を確認する（正常系）。"""
    # 準備
    save_mock.reset_mock()
    # 実行
    registry.remove("ai-monitor-sandbox-35-epic-conductor")
    # 検証
    assert registry.find("sandbox", "epic-conductor", 35) is None
    assert len(registry.sessions) == 2
    save_mock.assert_called_once()


def test_remove_when_missing(registry, save_mock):
    """該当なしの無視を確認する（正常系）。"""
    # 準備
    before = list(registry.sessions)
    # 実行
    registry.remove("ai-monitor-sandbox-99-unknown")
    # 検証
    assert registry.sessions == before


def test_release_by_number(registry, save_mock):
    """プロジェクト + 主番号一致の除去を確認する（正常系）。"""
    # 準備
    save_mock.reset_mock()
    # 実行
    released = registry.release_by_number("sandbox", 35)
    # 検証
    assert [s.session_name for s in released] == ["ai-monitor-sandbox-35-epic-conductor"]
    assert registry.find("other", "epic-conductor", 35) is not None
    save_mock.assert_called_once()


def test_release_by_number_when_no_match(registry, save_mock):
    """一致なしは空リストを確認する（正常系）。"""
    # 準備
    before = list(registry.sessions)
    # 実行
    released = registry.release_by_number("sandbox", 99)
    # 検証
    assert released == []
    assert registry.sessions == before
