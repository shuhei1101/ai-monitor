"""`src/ai_monitor/features/notify/gates.py` の単体テスト。"""
from __future__ import annotations

import pytest

from ai_monitor.features.notify.gates import notify_open_gates
from ai_monitor.features.sessions.types import AgentSession


class _Target:
    """MonitorTarget の最小スタブ。"""

    def __init__(self, number: int, labels: list[str], assignees: list[str]):
        self.number = number
        self.labels = labels
        self.assignees = assignees


@pytest.fixture
def notifier():
    """契機通知のスタブを返す（渡った引数を記録する）。"""
    calls: list[tuple] = []

    def _notify(event, title, body, *, repo=None, number=None):
        calls.append((event, title, body, repo, number))
        return None

    _notify.calls = calls
    return _notify


@pytest.fixture
def session() -> AgentSession:
    """ゲート未通知のセッションを返す。"""
    return AgentSession(
        session_name="ai-monitor-myproj-35-epic-conductor",
        project="myproj",
        agent_name="epic-conductor",
        primary_number=35,
    )


def test_notify_open_gates(notifier, session):
    """議論中 + assignee の対象を 1 度だけ通知する（正常系）。"""
    # 準備
    targets = [_Target(35, ["議論中", "確認:epic-conductor"], ["user"])]
    # 実行
    notify_open_gates(
        targets, [session], discussion_label="議論中", repo="owner/app", notify=notifier
    )
    # 検証
    assert len(notifier.calls) == 1
    event, title, body, repo, number = notifier.calls[0]
    assert event == "user_gate"
    assert "35" in title or "35" in body
    assert "epic-conductor" in body
    # 受け取った側が対象へ直接飛べるようリポジトリと番号が渡る
    assert (repo, number) == ("owner/app", 35)
    assert session.notified_gates == [35]


def test_notify_open_gates_when_already_notified(notifier, session):
    """通知済みの番号は再送しない（正常系）。"""
    # 準備
    session.notified_gates = [35]
    targets = [_Target(35, ["議論中"], ["user"])]
    # 実行
    notify_open_gates(targets, [session], discussion_label="議論中", repo="owner/app", notify=notifier)
    # 検証
    assert not notifier.calls


def test_notify_open_gates_when_gate_closed(notifier, session):
    """ゲートが閉じたら通知済み記録を落として次の開通に備える（正常系）。"""
    # 準備: 前周期にゲートを通知済みで、今周期は assignee が外れている
    session.notified_gates = [35]
    targets = [_Target(35, ["確認:epic-conductor"], [])]
    # 実行
    notify_open_gates(targets, [session], discussion_label="議論中", repo="owner/app", notify=notifier)
    # 検証
    assert not notifier.calls
    assert session.notified_gates == []


def test_notify_open_gates_when_not_watched(notifier, session):
    """自セッションの監視面にない番号は通知しない（正常系）。"""
    # 準備
    targets = [_Target(99, ["議論中"], ["user"])]
    # 実行
    notify_open_gates(targets, [session], discussion_label="議論中", repo="owner/app", notify=notifier)
    # 検証
    assert not notifier.calls
