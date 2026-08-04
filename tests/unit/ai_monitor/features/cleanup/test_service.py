"""`src/ai_monitor/features/cleanup/service.py` の単体テスト。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import ai_monitor.features.cleanup.service as cleanup
import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.shared.types import Issue, PullRequest


def _issue(number, labels=None, state="open"):
    return Issue(number=number, state=state, labels=labels or [], assignees=[])


def _pr(number, base="master", head="", linked=None, labels=None, state="open"):
    return PullRequest(
        number=number,
        state=state,
        labels=labels or [],
        assignees=[],
        linked_issue_numbers=linked or [],
        base_ref=base,
        head_ref=head or f"branch-{number}",
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
    """紐づく PR が全てマージされた intake のクローズを確認する（正常系）。"""
    # 準備（前周期には紐づく PR が 2 件、今周期は 0 件）
    prev = [_issue(30, labels=["layer:intake"]), _pr(40, linked=[30]), _pr(41, linked=[30])]
    targets = [_issue(30, labels=["layer:intake"]), _issue(31, labels=["layer:epic"])]
    # 実行
    cleanup.close_completed_intakes(mon_project, targets, prev, intake_label="layer:intake")
    # 検証
    io_mocks.close_issue.assert_called_once()
    assert io_mocks.close_issue.call_args.args[1] == 30


def test_close_completed_intakes_when_pr_open(io_mocks, mon_project):
    """未マージの PR が残る場合の見送りを確認する（正常系）。"""
    # 準備
    prev = [_issue(30, labels=["layer:intake"]), _pr(40, linked=[30]), _pr(41, linked=[30])]
    targets = [_issue(30, labels=["layer:intake"]), _pr(41, linked=[30])]
    # 実行
    cleanup.close_completed_intakes(mon_project, targets, prev, intake_label="layer:intake")
    # 検証
    io_mocks.close_issue.assert_not_called()


def test_close_completed_intakes_when_no_pr(io_mocks, mon_project):
    """PR 未作成の intake が対象外であることを確認する（正常系）。"""
    # 準備（前周期にも今周期にも紐づく PR が無い）
    prev = [_issue(30, labels=["layer:intake"])]
    targets = [_issue(30, labels=["layer:intake"])]
    # 実行
    cleanup.close_completed_intakes(mon_project, targets, prev, intake_label="layer:intake")
    # 検証
    io_mocks.close_issue.assert_not_called()


def test_release_closed_roots(io_mocks, registry, mon_project, notify):
    """配下の一括解放を確認する（正常系）。"""
    # 準備
    prev_targets = [_pr(35, base="master", head="feat/epic/x", linked=[30]), _pr(40, base="feat/epic/x")]
    targets = []
    io_mocks.get_issue.return_value = _issue(35, labels=["layer:epic"], state="closed")
    for number, agent in [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")]:
        registry.register(_session(agent=agent, number=number))
    # 実行
    cleanup.release_closed_roots(mon_project, targets, prev_targets, registry=registry, confirm_prefix="確認:", notify=notify)
    # 検証
    assert registry.sessions == []
    assert io_mocks.kill_session.call_count == 3


def test_release_closed_roots_when_confirm_remains(io_mocks, registry, mon_project, notify):
    """確認ラベル残存の見送りを確認する（正常系）。"""
    # 準備
    prev_targets = [
        _pr(35, base="master", head="feat/epic/x"),
        _pr(40, base="feat/epic/x", labels=["確認:subsystem-conductor"]),
    ]
    targets = [_pr(40, base="feat/epic/x", labels=["確認:subsystem-conductor"])]
    io_mocks.get_issue.return_value = _issue(35, labels=["layer:epic"], state="closed")
    registry.register(_session(number=35))
    # 実行
    cleanup.release_closed_roots(mon_project, targets, prev_targets, registry=registry, confirm_prefix="確認:", notify=notify)
    # 検証
    assert len(registry.sessions) == 1
    io_mocks.kill_session.assert_not_called()


def test_release_closed_roots_when_parent_remains(io_mocks, registry, mon_project, notify):
    """base が親レイヤーの面の見送りを確認する（正常系）。"""
    # 準備: base が system ブランチ（最上位ではない）
    prev_targets = [_pr(35, base="docs/system/x", head="feat/epic/x")]
    io_mocks.get_issue.return_value = _issue(35, labels=["layer:epic"], state="closed")
    registry.register(_session(number=35))
    # 実行
    cleanup.release_closed_roots(mon_project, [], prev_targets, registry=registry, confirm_prefix="確認:", notify=notify)
    # 検証
    assert len(registry.sessions) == 1
    io_mocks.kill_session.assert_not_called()
    assert notify.calls == []


def test_release_closed_roots_when_still_open(io_mocks, registry, mon_project, notify):
    """open のままの見送りを確認する（正常系）。"""
    # 準備
    prev_targets = [_issue(35, labels=["layer:epic"])]
    io_mocks.get_issue.side_effect = lambda project, number: _issue(35, labels=["layer:epic"], state="open")
    registry.register(_session(number=35))
    # 実行
    cleanup.release_closed_roots(mon_project, [], prev_targets, registry=registry, confirm_prefix="確認:", notify=notify)
    # 検証
    assert len(registry.sessions) == 1
    io_mocks.kill_session.assert_not_called()


def test_release_closed_roots_when_no_diff(io_mocks, registry, mon_project, notify):
    """差分なしの見送りを確認する（正常系）。"""
    # 準備
    epic = _issue(35, labels=["layer:epic"])
    # 実行
    cleanup.release_closed_roots(mon_project, [epic], [epic], registry=registry, confirm_prefix="確認:", notify=notify)
    # 検証
    io_mocks.get_issue.assert_not_called()


def test_is_root(mon_project):
    """base が master の PR を最上位と判定することを確認する（正常系）。"""
    targets = [_pr(35, base="master", head="feat/epic/x")]
    assert cleanup._is_root(targets[0], targets) is True


def test_is_root_when_upper_layer(mon_project):
    """base が親レイヤーの PR を最上位でないと判定することを確認する（正常系）。"""
    targets = [_pr(35, base="docs/system/x", head="feat/epic/x")]
    assert cleanup._is_root(targets[0], targets) is False


def test_collect_family_numbers():
    """base の連鎖で配下と起点 Issue を集めることを確認する（正常系）。"""
    # 準備（epic → story → subsystem の 3 段 + 起点 Issue）
    targets = [
        _pr(35, base="master", head="feat/epic/x", linked=[30]),
        _pr(40, base="feat/epic/x", head="feat/story/x/y"),
        _pr(50, base="feat/story/x/y", head="feat/be/x/y"),
    ]
    # 実行
    numbers = cleanup._collect_family_numbers(35, targets)
    # 検証
    assert sorted(numbers) == [30, 35, 40, 50]


def test_collect_family_numbers_when_no_linked_issue():
    """起点 Issue が無い場合に自身と子孫だけを返すことを確認する（正常系）。"""
    targets = [
        _pr(35, base="master", head="feat/epic/x"),
        _pr(40, base="feat/epic/x", head="feat/story/x/y"),
    ]
    assert sorted(cleanup._collect_family_numbers(35, targets)) == [35, 40]


def test_collect_family_numbers_when_artifact_pr():
    """成果物 PR も配下として集めることを確認する（正常系）。"""
    targets = [
        _pr(35, base="master", head="feat/epic/x"),
        _pr(36, base="feat/epic/x", head="docs/epic/x/mock"),
        _pr(40, base="feat/epic/x", head="feat/story/x/y"),
    ]
    assert sorted(cleanup._collect_family_numbers(35, targets)) == [35, 36, 40]


def _agent(name: str) -> Agent:
    return Agent(
        name=name,
        confirm_label=f"確認:{name}",
        processing_label=f"処理中:{name}",
        model="sonnet",
        effort="high",
    )


def test_release_closed_sessions(io_mocks, registry, mon_project):
    """close 確認後の解放とラベル除去を確認する（正常系）。"""
    # 準備: ワークフロー系のセッションも対象になる
    registry.register(_session(agent="story-conductor", number=60))
    io_mocks.get_issue.return_value = _issue(60, state="closed")
    # 実行
    cleanup.release_closed_sessions(mon_project, [], registry=registry, agents=[_agent("story-conductor")])
    # 検証
    assert registry.sessions == []
    io_mocks.kill_session.assert_called_once_with("ai-monitor-sandbox-60-story-conductor")
    removed = [call.args[2] for call in io_mocks.remove_label.call_args_list]
    assert removed == ["確認:story-conductor", "処理中:story-conductor"]


def test_release_closed_sessions_when_still_open(io_mocks, registry, mon_project):
    """open のままの見送りを確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="library-poc-runner", number=60))
    io_mocks.get_issue.return_value = _issue(60, state="open")
    # 実行
    cleanup.release_closed_sessions(mon_project, [], registry=registry, agents=[_agent("library-poc-runner")])
    # 検証
    assert len(registry.sessions) == 1
    io_mocks.kill_session.assert_not_called()
    io_mocks.remove_label.assert_not_called()


def test_release_closed_sessions_when_label_missing(io_mocks, registry, mon_project):
    """ラベル未付与でも解放が完了することを確認する（正常系）。"""
    # 準備: remove_label は未付与を無視する冪等操作
    registry.register(_session(agent="architect", number=52))
    io_mocks.get_issue.return_value = _issue(52, state="closed")
    # 実行
    cleanup.release_closed_sessions(mon_project, [], registry=registry, agents=[_agent("architect")])
    # 検証
    assert registry.sessions == []
    io_mocks.kill_session.assert_called_once_with("ai-monitor-sandbox-52-architect")


def test_reap_timed_out_sessions(io_mocks, registry, mon_project, rate_limit_gate, notify):
    """超過セッションの回収を確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="architect", number=52))
    targets = [_issue(52, labels=["確認:architect", "処理中:architect"])]
    agents = [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet", effort="high")]
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, targets, registry=registry, agents=agents, timeout_min=30, gate=rate_limit_gate, notify=notify)
    # 検証
    assert io_mocks.remove_label.call_args.args[2] == "処理中:architect"
    io_mocks.kill_session.assert_called_once_with("ai-monitor-sandbox-52-architect")
    assert registry.sessions == []


def test_reap_timed_out_sessions_when_waiting(io_mocks, registry, mon_project, rate_limit_gate, notify):
    """待機中の対象外を確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="architect", number=52))
    targets = [_issue(52, labels=["確認:architect"])]
    agents = [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet", effort="high")]
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, targets, registry=registry, agents=agents, timeout_min=30, gate=rate_limit_gate, notify=notify)
    # 検証
    io_mocks.kill_session.assert_not_called()
    io_mocks.remove_label.assert_not_called()
    assert len(registry.sessions) == 1


def test_reap_timed_out_sessions_when_session_gone(io_mocks, registry, mon_project, rate_limit_gate, notify):
    """実体消失の台帳修復を確認する（正常系）。"""
    # 準備
    registry.register(_session(agent="architect", number=52))
    io_mocks.has_session.return_value = False
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, [], registry=registry, agents=[], timeout_min=30, gate=rate_limit_gate, notify=notify)
    # 検証
    assert registry.sessions == []
    io_mocks.kill_session.assert_not_called()
    io_mocks.remove_label.assert_not_called()


def test_reap_timed_out_sessions_when_label_error(io_mocks, registry, mon_project, request_failed, rate_limit_gate, notify):
    """ラベル除去失敗の見送りを確認する（異常系）。"""
    # 準備
    registry.register(_session(agent="architect", number=52))
    targets = [_issue(52, labels=["処理中:architect"])]
    agents = [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet", effort="high")]
    io_mocks.remove_label.side_effect = request_failed(500)
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, targets, registry=registry, agents=agents, timeout_min=30, gate=rate_limit_gate, notify=notify)
    # 検証
    io_mocks.kill_session.assert_not_called()
    assert len(registry.sessions) == 1


def test_reap_timed_out_sessions_when_rate_limited(io_mocks, registry, mon_project, rate_limit_gate, notify):
    """レートリミット待機中の見送りを確認する（正常系）。"""
    # 準備: 回収条件を満たすセッションを用意したうえで関門を待機中にする
    registry.register(_session(agent="architect", number=52))
    targets = [_issue(52, labels=["確認:architect", "処理中:architect"])]
    agents = [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet", effort="high")]
    rate_limit_gate.block(
        "ai-monitor-sandbox-52-architect", datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    # 実行
    cleanup.reap_timed_out_sessions(mon_project, targets, registry=registry, agents=agents, timeout_min=30, gate=rate_limit_gate, notify=notify)
    # 検証: 止まっているのはハングではないので kill しない
    io_mocks.remove_label.assert_not_called()
    io_mocks.kill_session.assert_not_called()
    assert len(registry.sessions) == 1
