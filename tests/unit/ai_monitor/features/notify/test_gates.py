"""`src/ai_monitor/features/notify/gates.py` の単体テスト。"""
from __future__ import annotations

import pytest

from ai_monitor.features.notify.gates import notify_open_gates


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


def _call(targets, notified, notifier):
    notify_open_gates(
        targets,
        notified=notified,
        project="myproj",
        discussion_label="議論中",
        confirm_prefix="確認:",
        repo="owner/app",
        notify=notifier,
    )


def test_notify_open_gates(notifier):
    """議論中 + assignee の対象を 1 度だけ通知する（正常系）。"""
    # 準備
    notified: set[int] = set()
    targets = [_Target(35, ["議論中", "確認:epic-conductor"], ["user"])]
    # 実行
    _call(targets, notified, notifier)
    # 検証
    assert len(notifier.calls) == 1
    event, title, body, repo, number = notifier.calls[0]
    assert event == "user_gate"
    assert "35" in title or "35" in body
    # 担当は面の確認ラベルから引く（監視しているセッションの名前ではない）
    assert "epic-conductor" in body
    # 受け取った側が対象へ直接飛べるようリポジトリと番号が渡る
    assert (repo, number) == ("owner/app", 35)
    assert notified == {35}


def test_notify_open_gates_when_already_notified(notifier):
    """通知済みの番号は再送しない（正常系）。"""
    # 準備
    notified = {35}
    targets = [_Target(35, ["議論中", "確認:epic-conductor"], ["user"])]
    # 実行
    _call(targets, notified, notifier)
    # 検証
    assert not notifier.calls


def test_notify_open_gates_when_gate_closed(notifier):
    """ゲートが閉じたら通知済み記録を落として次の開通に備える（正常系）。"""
    # 準備: 前周期にゲートを通知済みで、今周期は assignee が外れている
    notified = {35}
    targets = [_Target(35, ["確認:epic-conductor"], [])]
    # 実行
    _call(targets, notified, notifier)
    # 検証
    assert not notifier.calls
    assert notified == set()


def test_notify_open_gates_when_multiple_watchers(notifier):
    """1 つの面を複数セッションが監視していても 1 度しか送らない（正常系）。"""
    # 準備: 記録がプロジェクト単位なので、周期をまたいでも増えない
    notified: set[int] = set()
    targets = [_Target(35, ["議論中", "確認:mock-reverse-engineer"], ["user"])]
    # 実行: 同じ周期の再入と次周期を模して 2 回呼ぶ
    _call(targets, notified, notifier)
    _call(targets, notified, notifier)
    # 検証
    assert len(notifier.calls) == 1
    assert "mock-reverse-engineer" in notifier.calls[0][2]


def test_notify_open_gates_when_no_confirm_label(notifier):
    """確認ラベルが無い面は担当を未割当として通知する（正常系）。"""
    # 準備: ユーザーが手で 議論中 + assignee を付けた面
    notified: set[int] = set()
    targets = [_Target(35, ["議論中"], ["user"])]
    # 実行
    _call(targets, notified, notifier)
    # 検証
    assert "未割当" in notifier.calls[0][2]


def test_notify_open_gates_when_not_open(notifier):
    """議論中でも assignee が無ければ通知しない（正常系）。"""
    # 準備
    notified: set[int] = set()
    targets = [_Target(99, ["議論中", "確認:architect"], [])]
    # 実行
    _call(targets, notified, notifier)
    # 検証
    assert not notifier.calls
