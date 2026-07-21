"""`src/ai_monitor/features/cleanup/service.py` の単体テスト。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ai_monitor.features.cleanup.service as cleanup
import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.shared.types import Issue


def _issue(number, labels=None, state="open", total=0, completed=0):
    return Issue(
        number=number,
        state=state,
        labels=labels or [],
        assignees=[],
        sub_issues_total=total,
        sub_issues_completed=completed,
    )


def _session(project="sandbox", agent="epic-conductor", number=35):
    return AgentSession(
        session_name=f"ai-monitor-{project}-{number}-{agent}",
        project=project,
        agent_name=agent,
        primary_number=number,
        last_seen_at="2026-07-20T00:00:00+09:00",
    )


@pytest.fixture
def io_mocks(monkeypatch):
    """GitHub / tmux 操作を MagicMock に差し替える。"""
    mocks = MagicMock()
    monkeypatch.setattr(cleanup, "close_issue", mocks.close_issue)
    monkeypatch.setattr(cleanup, "get_issue", mocks.get_issue)
    monkeypatch.setattr(cleanup, "get_parent_number", mocks.get_parent_number)
    monkeypatch.setattr(cleanup, "list_sub_issue_numbers", mocks.list_sub_issue_numbers)
    monkeypatch.setattr(cleanup, "remove_label", mocks.remove_label)
    monkeypatch.setattr(cleanup, "has_session", mocks.has_session)
    monkeypatch.setattr(cleanup, "kill_session", mocks.kill_session)
    mocks.has_session.return_value = True
    return mocks


@pytest.fixture
def registry(tmp_state_path, monkeypatch):
    monkeypatch.setattr(registry_mod, "save_sessions", MagicMock())
    return registry_mod.SessionRegistry(tmp_state_path)


def test_close_completed_intakes(io_mocks, mon_project):
    """全子 closed のクローズを確認する（正常系）。"""
    # 準備
    targets = [
        _issue(30, labels=["layer:intake"], total=2, completed=2),
        _issue(31, labels=["layer:epic"], total=2, completed=2),
    ]
    # 実行
    cleanup.close_completed_intakes(mon_project, targets)
    # 検証
    io_mocks.close_issue.assert_called_once()
    assert io_mocks.close_issue.call_args.args[1] == 30


def test_close_completed_intakes_when_incomplete(io_mocks, mon_project):
    """未完了の見送りを確認する（正常系）。"""
    # 準備
    targets = [_issue(30, labels=["layer:intake"], total=2, completed=1)]
    # 実行
    cleanup.close_completed_intakes(mon_project, targets)
    # 検証
    io_mocks.close_issue.assert_not_called()


def test_close_completed_intakes_when_no_children(io_mocks, mon_project):
    """Sub-issue なしの対象外を確認する（正常系）。"""
    # 準備
    targets = [_issue(30, labels=["layer:intake"], total=0, completed=0)]
    # 実行
    cleanup.close_completed_intakes(mon_project, targets)
    # 検証
    io_mocks.close_issue.assert_not_called()


def test_release_closed_epics(io_mocks, registry, mon_project):
    """配下の一括解放を確認する（正常系）。"""
    # 準備
    prev_targets = [_issue(35, labels=["layer:epic"])]
    targets = []
    io_mocks.get_issue.return_value = _issue(35, labels=["layer:epic"], state="closed")
    io_mocks.list_sub_issue_numbers.side_effect = lambda project, number: {35: [40], 40: []}[number]
    io_mocks.get_parent_number.return_value = 30
    for number, agent in [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")]:
        registry.register(_session(agent=agent, number=number))
    # 実行
    cleanup.release_closed_epics(mon_project, targets, prev_targets, registry=registry)
    # 検証
    assert registry.sessions == []
    assert io_mocks.kill_session.call_count == 3


def test_release_closed_epics_when_confirm_remains(io_mocks, registry, mon_project):
    """確認ラベル残存の見送りを確認する（正常系）。"""
    # 準備
    prev_targets = [_issue(35, labels=["layer:epic"])]
    targets = [_issue(40, labels=["layer:subsystem", "確認:subsystem-conductor"])]
    io_mocks.get_issue.return_value = _issue(35, labels=["layer:epic"], state="closed")
    io_mocks.list_sub_issue_numbers.side_effect = lambda project, number: {35: [40], 40: []}[number]
    io_mocks.get_parent_number.return_value = None
    registry.register(_session(number=35))
    # 実行
    cleanup.release_closed_epics(mon_project, targets, prev_targets, registry=registry)
    # 検証
    assert len(registry.sessions) == 1
    io_mocks.kill_session.assert_not_called()


def test_release_closed_epics_when_still_open(io_mocks, registry, mon_project):
    """open のままの見送りを確認する（正常系）。"""
    # 準備
    prev_targets = [_issue(35, labels=["layer:epic"])]
    io_mocks.get_issue.return_value = _issue(35, labels=["layer:epic"], state="open")
    registry.register(_session(number=35))
    # 実行
    cleanup.release_closed_epics(mon_project, [], prev_targets, registry=registry)
    # 検証
    assert len(registry.sessions) == 1
    io_mocks.kill_session.assert_not_called()


def test_release_closed_epics_when_no_diff(io_mocks, registry, mon_project):
    """差分なしの見送りを確認する（正常系）。"""
    # 準備
    epic = _issue(35, labels=["layer:epic"])
    # 実行
    cleanup.release_closed_epics(mon_project, [epic], [epic], registry=registry)
    # 検証
    io_mocks.get_issue.assert_not_called()


def test_collect_family_numbers(io_mocks, mon_project):
    """2 段の再帰と親の合算を確認する（正常系）。"""
    # 準備
    io_mocks.list_sub_issue_numbers.side_effect = lambda project, number: {35: [40], 40: [50], 50: []}[number]
    io_mocks.get_parent_number.return_value = 30
    # 実行
    numbers = cleanup._collect_family_numbers(mon_project, 35)
    # 検証
    assert sorted(numbers) == [30, 35, 40, 50]


def test_collect_family_numbers_when_no_parent(io_mocks, mon_project):
    """親なし epic を確認する（正常系）。"""
    # 準備
    io_mocks.list_sub_issue_numbers.side_effect = lambda project, number: {35: []}[number]
    io_mocks.get_parent_number.return_value = None
    # 実行
    numbers = cleanup._collect_family_numbers(mon_project, 35)
    # 検証
    assert numbers == [35]


def test_release_closed_standalone(io_mocks, registry, mon_project):
    """close 確認後の解放を確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="library-poc-runner", number=60))
    io_mocks.get_issue.return_value = _issue(60, state="closed")
    # 実行
    cleanup.release_closed_standalone(mon_project, [], registry=registry, standalone_names={"library-poc-runner"})
    # 検証
    assert registry.sessions == []
    io_mocks.kill_session.assert_called_once_with("ai-monitor-sandbox-60-library-poc-runner")


def test_release_closed_standalone_when_still_open(io_mocks, registry, mon_project):
    """open のままの見送りを確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="library-poc-runner", number=60))
    io_mocks.get_issue.return_value = _issue(60, state="open")
    # 実行
    cleanup.release_closed_standalone(mon_project, [], registry=registry, standalone_names={"library-poc-runner"})
    # 検証
    assert len(registry.sessions) == 1
    io_mocks.kill_session.assert_not_called()


def test_release_closed_standalone_when_workflow_agent(io_mocks, registry, mon_project):
    """ワークフロー系の対象外を確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="epic-conductor", number=35))
    # 実行
    cleanup.release_closed_standalone(mon_project, [], registry=registry, standalone_names={"library-poc-runner"})
    # 検証
    io_mocks.get_issue.assert_not_called()
    assert len(registry.sessions) == 1


def test_reap_timed_out_sessions(io_mocks, registry, mon_project):
    """超過セッションの回収を確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="architect", number=52))
    targets = [_issue(52, labels=["確認:architect", "処理中:architect"])]
    agents = [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet")]
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, targets, registry=registry, agents=agents, timeout_min=30)
    # 検証
    assert io_mocks.remove_label.call_args.args[2] == "処理中:architect"
    io_mocks.kill_session.assert_called_once_with("ai-monitor-sandbox-52-architect")
    assert registry.sessions == []


def test_reap_timed_out_sessions_when_waiting(io_mocks, registry, mon_project):
    """待機中の対象外を確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="architect", number=52))
    targets = [_issue(52, labels=["確認:architect"])]
    agents = [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet")]
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, targets, registry=registry, agents=agents, timeout_min=30)
    # 検証
    io_mocks.kill_session.assert_not_called()
    io_mocks.remove_label.assert_not_called()
    assert len(registry.sessions) == 1


def test_reap_timed_out_sessions_when_session_gone(io_mocks, registry, mon_project):
    """実体消失の台帳修復を確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="architect", number=52))
    io_mocks.has_session.return_value = False
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, [], registry=registry, agents=[], timeout_min=30)
    # 検証
    assert registry.sessions == []
    io_mocks.kill_session.assert_not_called()
    io_mocks.remove_label.assert_not_called()


def test_reap_timed_out_sessions_when_label_error(io_mocks, registry, mon_project, request_failed):
    """ラベル除去失敗の見送りを確認する（異常系）。"""
    # 準備
    registry.register(_session(agent="architect", number=52))
    targets = [_issue(52, labels=["処理中:architect"])]
    agents = [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet")]
    io_mocks.remove_label.side_effect = request_failed(500)
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, targets, registry=registry, agents=agents, timeout_min=30)
    # 検証
    io_mocks.kill_session.assert_not_called()
    assert len(registry.sessions) == 1
