"""`src/ai_monitor/features/agents/service.py` の単体テスト。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ai_monitor.features.agents.service as service
import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.shared.types import Issue, PullRequest


@pytest.fixture
def agent() -> Agent:
    return Agent(
        name="intake-issue-triager",
        confirm_label="確認:intake-issue-triager",
        processing_label="処理中:intake-issue-triager",
    )


@pytest.fixture
def io_mocks(monkeypatch):
    """GitHub / tmux 操作を MagicMock に差し替える。"""
    mocks = MagicMock()
    monkeypatch.setattr(service, "add_label", mocks.add_label)
    monkeypatch.setattr(service, "create_session", mocks.create_session)
    monkeypatch.setattr(service, "send_keys", mocks.send_keys)
    return mocks


@pytest.fixture
def registry(tmp_state_path, monkeypatch):
    monkeypatch.setattr(registry_mod, "save_sessions", MagicMock())
    return registry_mod.SessionRegistry(tmp_state_path)


def _issue(number, labels=None, assignees=None):
    return Issue(number=number, state="open", labels=labels or [], assignees=assignees or [])


def test_poll_when_mixed_targets(agent, io_mocks, registry, mon_project):
    """確認ラベル + assignee なしの絞り込みを確認する（正常系）。"""
    # 準備
    targets = [
        _issue(35, labels=["確認:intake-issue-triager"]),
        _issue(36, labels=["確認:intake-issue-triager"], assignees=["shuhei1101"]),
        _issue(37, labels=["layer:epic"]),
    ]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry)
    # 検証
    assert io_mocks.send_keys.call_count == 1
    assert "35" in io_mocks.send_keys.call_args.args[0]


def test_poll_when_new_target(agent, io_mocks, registry, mon_project):
    """新規対象にセッション作成 + skill 起動を確認する（正常系）。"""
    # 準備
    targets = [_issue(35, labels=["確認:intake-issue-triager"])]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry)
    # 検証
    session_name = "ai-monitor-sandbox-35-intake-issue-triager"
    assert io_mocks.create_session.call_args.args[0] == session_name
    assert registry.find("sandbox", "intake-issue-triager", 35) is not None
    sent_text = io_mocks.send_keys.call_args.args[1]
    assert sent_text.startswith('claude --dangerously-skip-permissions "/ai-monitor:intake-issue-triager 35')


def test_poll_when_existing_session(agent, io_mocks, registry, mon_project):
    """既存セッションへの send-keys を確認する（正常系）。"""
    # 準備
    registry.register(
        AgentSession(
            session_name="ai-monitor-sandbox-35-intake-issue-triager",
            project="sandbox",
            agent_name="intake-issue-triager",
            primary_number=35,
        )
    )
    targets = [_issue(35, labels=["確認:intake-issue-triager"])]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry)
    # 検証
    io_mocks.create_session.assert_not_called()
    assert io_mocks.send_keys.call_args.args[0] == "ai-monitor-sandbox-35-intake-issue-triager"
    assert io_mocks.send_keys.call_args.args[1].startswith("状態が変化しました")


def test_poll_when_processing_label(agent, io_mocks, registry, mon_project):
    """処理中ラベル付きの対象の除外を確認する（正常系）。"""
    # 準備
    targets = [_issue(35, labels=["確認:intake-issue-triager", "処理中:intake-issue-triager"])]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry)
    # 検証
    io_mocks.send_keys.assert_not_called()
    io_mocks.add_label.assert_not_called()


def test_poll_when_priority_labels(agent, io_mocks, registry, mon_project):
    """優先度ソート順の処理を確認する（正常系）。"""
    # 準備
    targets = [
        _issue(35, labels=["確認:intake-issue-triager", "優先度:いつでも"]),
        _issue(36, labels=["確認:intake-issue-triager", "優先度:急ぎ"]),
    ]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry)
    # 検証
    sent_sessions = [c.args[0] for c in io_mocks.send_keys.call_args_list]
    assert sent_sessions == [
        "ai-monitor-sandbox-36-intake-issue-triager",
        "ai-monitor-sandbox-35-intake-issue-triager",
    ]


def test_build_skill_command():
    """起動文字列の組み立てを確認する（正常系）。"""
    # 準備
    agent = Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect")
    # 実行
    command = service.build_skill_command(agent, 52)
    # 検証
    assert command == "/ai-monitor:architect 52"


def test_process_one(agent, io_mocks, registry, mon_project):
    """送信前後の処理中ラベル付け外しを確認する（正常系）。"""
    # 準備
    target = _issue(35, labels=["確認:intake-issue-triager"])
    # 実行
    service._process_one(mon_project, agent, target, open_targets=[target], registry=registry)
    # 検証
    assert io_mocks.add_label.call_args.args[2] == "処理中:intake-issue-triager"
    sent_text = io_mocks.send_keys.call_args.args[1]
    assert sent_text.startswith('claude --dangerously-skip-permissions "/ai-monitor:intake-issue-triager 35')
    assert "#35" in sent_text


def test_sort_key():
    """同ランクは番号昇順を確認する（正常系）。"""
    # 準備
    first = _issue(35)
    second = _issue(40)
    # 実行・検証
    assert service._sort_key(first) == (1, 35)
    assert service._sort_key(first) < service._sort_key(second)


def test_build_context_snapshot():
    """Issue 起点の PR ぶら下げを確認する（正常系）。"""
    # 準備
    issue = _issue(50, labels=["layer:subsystem"])
    draft_pr = PullRequest(number=52, state="open", labels=["確認:architect"], linked_issue_numbers=[50])
    poc_pr = PullRequest(number=60, state="open", labels=["確認:library-poc-runner"], linked_issue_numbers=[50])
    other_pr = PullRequest(number=99, state="open", linked_issue_numbers=[90])
    # 実行
    snapshot = service.build_context_snapshot(issue, [issue, draft_pr, poc_pr, other_pr])
    # 検証
    assert "#50" in snapshot and "#52" in snapshot and "#60" in snapshot
    assert "#99" not in snapshot
    assert "確認:architect" in snapshot
    assert "[open]" in snapshot


def test_build_context_snapshot_when_pr_target():
    """PR 起点の基準解決を確認する（正常系）。"""
    # 準備
    issue = _issue(50, labels=["layer:subsystem"])
    pr = PullRequest(number=52, state="open", labels=["確認:architect"], linked_issue_numbers=[50])
    sibling = PullRequest(number=60, state="open", linked_issue_numbers=[50])
    # 実行
    from_pr = service.build_context_snapshot(pr, [issue, pr, sibling])
    from_issue = service.build_context_snapshot(issue, [issue, pr, sibling])
    # 検証
    assert from_pr == from_issue


def test_build_context_snapshot_when_linked_issue_not_open():
    """紐づく Issue が open 一覧に無い場合を確認する（正常系）。"""
    # 準備
    pr = PullRequest(number=52, state="open", labels=["確認:architect"], linked_issue_numbers=[50])
    # 実行
    snapshot = service.build_context_snapshot(pr, [pr])
    # 検証
    assert "#52" in snapshot
    assert "#50" not in snapshot
