"""`src/ai_monitor/features/agents/service.py` の単体テスト。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ai_monitor.features.agents.service as service
import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.shared.settings import TelemetrySettings
from ai_monitor.shared.types import Issue, PullRequest

WIKI_BASE = "/repo/ai-monitor/docs/wiki"


@pytest.fixture
def agent() -> Agent:
    return Agent(
        name="intake-issue-triager",
        confirm_label="確認:intake-issue-triager",
        processing_label="処理中:intake-issue-triager",
        model="opus",
    )


@pytest.fixture
def io_mocks(monkeypatch):
    """GitHub / tmux 操作を MagicMock に差し替える。"""
    mocks = MagicMock()
    monkeypatch.setattr(service, "add_label", mocks.add_label)
    monkeypatch.setattr(service, "create_session", mocks.create_session)
    monkeypatch.setattr(service, "send_keys", mocks.send_keys)
    mocks.build_agent_docs.return_value = "## フェーズ\n\n# 初期処理\n"
    monkeypatch.setattr(service, "build_agent_docs", mocks.build_agent_docs)
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
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE)
    # 検証
    assert io_mocks.send_keys.call_count == 1
    assert "35" in io_mocks.send_keys.call_args.args[0]


def test_poll_when_new_target(agent, io_mocks, registry, mon_project):
    """新規対象にセッション作成 + skill 起動を確認する（正常系）。"""
    # 準備
    targets = [_issue(35, labels=["確認:intake-issue-triager"])]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE)
    # 検証
    session_name = "ai-monitor-sandbox-35-intake-issue-triager"
    assert io_mocks.create_session.call_args.args[0] == session_name
    assert registry.find("sandbox", "intake-issue-triager", 35) is not None
    sent_text = io_mocks.send_keys.call_args.args[1]
    assert sent_text.startswith("AI_MONITOR_PROJECT=sandbox AI_MONITOR_AGENT=intake-issue-triager")
    assert 'claude --model opus --dangerously-skip-permissions "$(cat ' in sent_text


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
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE)
    # 検証
    io_mocks.create_session.assert_not_called()
    assert io_mocks.send_keys.call_args.args[0] == "ai-monitor-sandbox-35-intake-issue-triager"
    assert io_mocks.send_keys.call_args.args[1].startswith("状態が変化しました")


def test_poll_when_processing_label(agent, io_mocks, registry, mon_project):
    """処理中ラベル付きの対象の除外を確認する（正常系）。"""
    # 準備
    targets = [_issue(35, labels=["確認:intake-issue-triager", "処理中:intake-issue-triager"])]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE)
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
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE)
    # 検証
    sent_sessions = [c.args[0] for c in io_mocks.send_keys.call_args_list]
    assert sent_sessions == [
        "ai-monitor-sandbox-36-intake-issue-triager",
        "ai-monitor-sandbox-35-intake-issue-triager",
    ]


def test_build_launch_prompt(agent, io_mocks, mon_project):
    """起動プロンプトの組み立てを確認する（正常系）。"""
    # 実行
    prompt = service.build_launch_prompt(
        agent, 52, mon_project, "Issue #52 [open]", ai_monitor_wiki_base=WIKI_BASE
    )
    # 検証: エージェント名・対象番号・ドキュメント・スナップショットが含まれる
    assert "intake-issue-triager" in prompt
    assert "52" in prompt
    assert "# 初期処理" in prompt
    assert "Issue #52 [open]" in prompt


def test_process_one(agent, io_mocks, registry, mon_project):
    """送信前後の処理中ラベル付け外しを確認する（正常系）。"""
    # 準備
    target = _issue(35, labels=["確認:intake-issue-triager"])
    # 実行
    service._process_one(
        mon_project, agent, target, open_targets=[target], registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE
    )
    # 検証
    assert io_mocks.add_label.call_args.args[2] == "処理中:intake-issue-triager"
    sent_text = io_mocks.send_keys.call_args.args[1]
    assert sent_text.startswith("AI_MONITOR_PROJECT=sandbox ")
    assert 'claude --model opus --dangerously-skip-permissions "$(cat ' in sent_text


def test_process_one_when_new_session(agent, io_mocks, registry, mon_project):
    """新規セッションの起動コマンドを確認する（正常系）。"""
    # 準備
    target = _issue(35, labels=["確認:intake-issue-triager"])
    # 実行
    service._process_one(
        mon_project, agent, target, open_targets=[target], registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE
    )
    # 検証
    assert io_mocks.create_session.call_args.args[0] == "ai-monitor-sandbox-35-intake-issue-triager"
    assert "claude --model opus " in io_mocks.send_keys.call_args.args[1]
    # 起動プロンプトは一時ファイル経由で渡す（数万文字を send-keys の引数に直接埋めない）
    assert '"$(cat ' in io_mocks.send_keys.call_args.args[1]


def test_build_launch_env(mon_project, agent):
    """環境変数の組み立てを確認する（正常系）。"""
    # 準備
    telemetry = TelemetrySettings(otlp_endpoint="http://localhost:14317")
    # 実行
    env = service.build_launch_env(telemetry, mon_project, agent, 131, 8765)
    # 検証
    assert "AI_MONITOR_PROJECT=sandbox" in env
    assert "CLAUDE_CODE_ENABLE_TELEMETRY=1" in env
    assert "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1" in env
    assert "OTEL_LOGS_EXPORTER=otlp" in env
    assert "OTEL_TRACES_EXPORTER=otlp" in env
    assert "OTEL_METRICS_EXPORTER=otlp" in env
    assert "OTEL_EXPORTER_OTLP_PROTOCOL=grpc" in env
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:14317" in env
    assert "OTEL_LOG_USER_PROMPTS=1" in env
    assert "OTEL_LOG_ASSISTANT_RESPONSES=1" in env
    assert "OTEL_LOG_TOOL_DETAILS=1" in env
    assert "OTEL_LOG_TOOL_CONTENT=1" in env
    assert env.endswith(" ")


def test_build_launch_env_when_telemetry_unset(mon_project, agent):
    """テレメトリなしを確認する（正常系）。"""
    # 実行
    env = service.build_launch_env(None, mon_project, agent, 131, 8765)
    # 検証: フック向けの 4 変数だけが返る
    assert env == (
        "AI_MONITOR_PROJECT=sandbox AI_MONITOR_AGENT=intake-issue-triager "
        "AI_MONITOR_NUMBER=131 AI_MONITOR_PORT=8765 "
    )
    assert "OTEL_" not in env


def test_build_launch_env_when_resource_attributes(mon_project, agent):
    """識別子の埋め込みを確認する（正常系）。"""
    # 準備
    telemetry = TelemetrySettings(otlp_endpoint="http://localhost:4317")
    # 実行
    env = service.build_launch_env(telemetry, mon_project, agent, 131, 8765)
    # 検証
    assert (
        "OTEL_RESOURCE_ATTRIBUTES="
        "ai_monitor.project=sandbox,"
        "ai_monitor.agent=intake-issue-triager,"
        "ai_monitor.number=131" in env
    )


def test_process_one_when_telemetry_set(agent, io_mocks, registry, mon_project):
    """テレメトリ環境変数の前置を確認する（正常系）。"""
    # 準備
    target = _issue(35, labels=["確認:intake-issue-triager"])
    telemetry = TelemetrySettings(otlp_endpoint="http://localhost:4317")
    # 実行
    service._process_one(
        mon_project, agent, target, open_targets=[target], registry=registry, telemetry=telemetry, port=8765, ai_monitor_wiki_base=WIKI_BASE
    )
    # 検証
    sent_text = io_mocks.send_keys.call_args.args[1]
    assert sent_text.startswith("AI_MONITOR_PROJECT=sandbox AI_MONITOR_AGENT=")
    assert "CLAUDE_CODE_ENABLE_TELEMETRY=1 " in sent_text
    assert "ai_monitor.number=35" in sent_text
    assert " claude --model opus " in sent_text


def test_process_one_when_telemetry_unset(agent, io_mocks, registry, mon_project):
    """テレメトリなしの起動コマンドを確認する（正常系）。"""
    # 準備
    target = _issue(35, labels=["確認:intake-issue-triager"])
    # 実行
    service._process_one(
        mon_project, agent, target, open_targets=[target], registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE
    )
    # 検証
    sent_text = io_mocks.send_keys.call_args.args[1]
    assert sent_text.startswith("AI_MONITOR_PROJECT=sandbox AI_MONITOR_AGENT=")
    assert "OTEL_" not in sent_text


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


def test_build_launch_env_when_hook_variables(mon_project, agent):
    """フック向け変数の埋め込みを確認する（正常系）。"""
    # 準備
    telemetry = TelemetrySettings(otlp_endpoint="http://localhost:4317")
    # 実行
    env = service.build_launch_env(telemetry, mon_project, agent, 52, 8765)
    # 検証: コンパクト通知の宛先と素性が入る
    assert "AI_MONITOR_AGENT=intake-issue-triager" in env
    assert "AI_MONITOR_NUMBER=52" in env
    assert "AI_MONITOR_PORT=8765" in env
