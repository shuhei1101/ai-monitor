"""`src/ai_monitor/main.py` の単体テスト。"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from githubkit.exception import RequestFailed

import ai_monitor.main as main_mod
import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.shared.types import Issue

STANDALONE_NAMES = {"epic-poc-runner", "library-poc-runner", "resetter", "quick-implementer", "questioner"}


def test_build_agents(label_settings):
    """全エージェント分の Agent 生成を確認する（正常系）。"""
    # 実行
    agents = main_mod.build_agents(label_settings)
    # 検証
    assert len(agents) == 17
    by_name = {a.name: a for a in agents}
    assert by_name["epic-conductor"].confirm_label == "確認:epic-conductor"
    assert by_name["epic-conductor"].processing_label == "処理中:epic-conductor"
    assert {a.name for a in agents if a.standalone} == STANDALONE_NAMES


@pytest.fixture
def cycle_mocks(monkeypatch):
    """run_cycle の依存関数を MagicMock に差し替える。"""
    mocks = MagicMock()
    mocks.list_open_targets.return_value = [Issue(number=35, state="open")]
    monkeypatch.setattr(main_mod, "list_open_targets", mocks.list_open_targets)
    monkeypatch.setattr(main_mod, "poll", mocks.poll)
    monkeypatch.setattr(main_mod, "close_completed_intakes", mocks.close_completed_intakes)
    monkeypatch.setattr(main_mod, "release_closed_epics", mocks.release_closed_epics)
    monkeypatch.setattr(main_mod, "release_closed_standalone", mocks.release_closed_standalone)
    monkeypatch.setattr(main_mod, "reap_timed_out_sessions", mocks.reap_timed_out_sessions)
    return mocks


@pytest.fixture
def cycle_env(tmp_state_path, monkeypatch, mon_project, label_settings):
    """run_cycle 用の設定・エージェント・台帳を組み立てる。"""
    monkeypatch.setattr(registry_mod, "save_sessions", MagicMock())
    settings = MagicMock()
    settings.projects = [mon_project]
    settings.heartbeat_interval_sec = 60
    settings.session_timeout_min = 30
    agents = main_mod.build_agents(label_settings)
    registry = registry_mod.SessionRegistry(tmp_state_path)
    return settings, agents, registry


def test_run_cycle(cycle_mocks, cycle_env):
    """1 周期の配線を確認する（正常系）。"""
    # 準備
    settings, agents, registry = cycle_env
    # 実行
    targets_by_project, _ = main_mod.run_cycle(
        settings, agents, registry=registry, prev_targets={}, last_heartbeat_at="2100-01-01T00:00:00+00:00"
    )
    # 検証
    assert cycle_mocks.list_open_targets.call_count == 1
    assert cycle_mocks.poll.call_count == len(agents)
    cycle_mocks.close_completed_intakes.assert_called_once()
    cycle_mocks.release_closed_epics.assert_called_once()
    cycle_mocks.release_closed_standalone.assert_called_once()
    assert targets_by_project["sandbox"] == cycle_mocks.list_open_targets.return_value


def test_run_cycle_when_heartbeat_elapsed(cycle_mocks, cycle_env):
    """heartbeat 経過時のタイムアウト回収を確認する（正常系）。"""
    # 準備
    settings, agents, registry = cycle_env
    # 実行
    _, heartbeat_at = main_mod.run_cycle(
        settings, agents, registry=registry, prev_targets={}, last_heartbeat_at="2000-01-01T00:00:00+00:00"
    )
    # 検証
    cycle_mocks.reap_timed_out_sessions.assert_called_once()
    assert heartbeat_at != "2000-01-01T00:00:00+00:00"


def test_run_cycle_when_heartbeat_not_elapsed(cycle_mocks, cycle_env):
    """heartbeat 未経過のスキップを確認する（正常系）。"""
    # 準備
    settings, agents, registry = cycle_env
    now = datetime.now(timezone.utc).isoformat()
    # 実行
    _, heartbeat_at = main_mod.run_cycle(
        settings, agents, registry=registry, prev_targets={}, last_heartbeat_at=now
    )
    # 検証
    cycle_mocks.reap_timed_out_sessions.assert_not_called()
    assert heartbeat_at == now


def test_run_cycle_when_list_error(cycle_mocks, cycle_env):
    """一覧取得失敗の周期見送りを確認する（異常系）。"""
    # 準備
    settings, agents, registry = cycle_env
    response = MagicMock()
    response.status_code = 500
    cycle_mocks.list_open_targets.side_effect = RequestFailed(response)
    # 実行
    targets_by_project, _ = main_mod.run_cycle(
        settings, agents, registry=registry, prev_targets={}, last_heartbeat_at="2100-01-01T00:00:00+00:00"
    )
    # 検証
    cycle_mocks.poll.assert_not_called()
    assert targets_by_project == {}
