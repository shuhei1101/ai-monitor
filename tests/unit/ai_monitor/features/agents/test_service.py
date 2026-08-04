"""`src/ai_monitor/features/agents/service.py` の単体テスト。"""
from __future__ import annotations

import json
import shlex
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import ai_monitor.features.agents.service as service
import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.features.agents.docs import PhaseConfig
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.integrations.github.stacks import Stack
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
        effort="xhigh",
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
    mocks.load_phase_config.return_value = PhaseConfig(
        phases={"intake-issue-triager": ["エージェント/intake-issue-triager/フェーズ/初期処理.md"]}
    )
    monkeypatch.setattr(service, "load_phase_config", mocks.load_phase_config)
    # スタック所属の照会は既定で未所属にする（下位が open の側は各テストで上書きする）
    mocks.get_stack.return_value = None
    monkeypatch.setattr(service, "get_stack", mocks.get_stack)
    return mocks


@pytest.fixture
def registry(tmp_state_path, monkeypatch):
    monkeypatch.setattr(registry_mod, "save_sessions", MagicMock())
    return registry_mod.SessionRegistry(tmp_state_path)


def _issue(number, labels=None, assignees=None):
    return Issue(number=number, state="open", labels=labels or [], assignees=assignees or [])


def _pr(number, base="master", head="", labels=None, assignees=None, linked=None):
    return PullRequest(
        number=number,
        state="open",
        labels=labels or [],
        assignees=assignees or [],
        linked_issue_numbers=linked or [],
        base_ref=base,
        head_ref=head or f"branch-{number}",
    )


def test_poll_when_mixed_targets(agent, io_mocks, registry, mon_project, rate_limit_gate):
    """確認ラベル + assignee なしの絞り込みを確認する（正常系）。"""
    # 準備
    targets = [
        _issue(35, labels=["確認:intake-issue-triager"]),
        _issue(36, labels=["確認:intake-issue-triager"], assignees=["shuhei1101"]),
        _issue(37, labels=["layer:epic"]),
    ]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE, priority_urgent="優先度:急ぎ", priority_low="優先度:いつでも", gate=rate_limit_gate)
    # 検証
    assert io_mocks.send_keys.call_count == 1
    assert "35" in io_mocks.send_keys.call_args.args[0]


def test_poll_when_new_target(agent, io_mocks, registry, mon_project, rate_limit_gate):
    """新規対象にセッション作成 + skill 起動を確認する（正常系）。"""
    # 準備
    targets = [_issue(35, labels=["確認:intake-issue-triager"])]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE, priority_urgent="優先度:急ぎ", priority_low="優先度:いつでも", gate=rate_limit_gate)
    # 検証
    session_name = "ai-monitor-sandbox-35-intake-issue-triager"
    assert io_mocks.create_session.call_args.args[0] == session_name
    assert registry.find("sandbox", "intake-issue-triager", 35) is not None
    sent_text = io_mocks.send_keys.call_args.args[1]
    assert sent_text.startswith("AI_MONITOR_PROJECT=sandbox AI_MONITOR_AGENT=intake-issue-triager")
    assert "claude --model opus --effort xhigh --dangerously-skip-permissions" in sent_text
    assert "--append-system-prompt-file " in sent_text


def test_poll_when_existing_session(agent, io_mocks, registry, mon_project, rate_limit_gate):
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
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE, priority_urgent="優先度:急ぎ", priority_low="優先度:いつでも", gate=rate_limit_gate)
    # 検証
    io_mocks.create_session.assert_not_called()
    assert io_mocks.send_keys.call_args.args[0] == "ai-monitor-sandbox-35-intake-issue-triager"
    assert io_mocks.send_keys.call_args.args[1].startswith("状態が変化しました")


def test_poll_when_processing_label(agent, io_mocks, registry, mon_project, rate_limit_gate):
    """処理中ラベル付きの対象の除外を確認する（正常系）。"""
    # 準備
    targets = [_issue(35, labels=["確認:intake-issue-triager", "処理中:intake-issue-triager"])]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE, priority_urgent="優先度:急ぎ", priority_low="優先度:いつでも", gate=rate_limit_gate)
    # 検証
    io_mocks.send_keys.assert_not_called()
    io_mocks.add_label.assert_not_called()


def test_poll_when_rate_limited(agent, io_mocks, registry, mon_project, rate_limit_gate):
    """レートリミット待機中の見送りを確認する（正常系）。"""
    # 準備: 起動条件を満たす対象を用意したうえで関門を待機中にする
    targets = [_issue(35, labels=["確認:intake-issue-triager"])]
    rate_limit_gate.block(
        "ai-monitor-sandbox-35-intake-issue-triager", datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    # 実行
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE, priority_urgent="優先度:急ぎ", priority_low="優先度:いつでも", gate=rate_limit_gate)
    # 検証: 起動しても枠を消費して止まるだけなので何もしない
    io_mocks.create_session.assert_not_called()
    io_mocks.add_label.assert_not_called()
    io_mocks.send_keys.assert_not_called()


def test_poll_when_stack_below_open(agent, io_mocks, registry, mon_project, rate_limit_gate):
    """スタック下位に open な PR が残っている対象を送らないことを確認する（正常系）。"""
    # 準備: 対象がスタックに属し、自分より下に open な PR がある
    io_mocks.get_stack.return_value = Stack(number=90, position=1, pull_requests=[34, 35], below_open=[34])
    targets = [_pr(35, labels=["確認:intake-issue-triager"])]
    # 実行
    service.poll(
        mon_project,
        agent,
        targets,
        registry=registry,
        telemetry=None,
        port=8765,
        ai_monitor_wiki_base="https://example.com/wiki",
        priority_urgent="優先度:急ぎ",
        priority_low="優先度:いつでも",
        gate=rate_limit_gate,
    )
    # 検証: セッション作成も送信も処理中ラベルの付与も起きない
    io_mocks.create_session.assert_not_called()
    io_mocks.send_keys.assert_not_called()
    io_mocks.add_label.assert_not_called()
    assert registry.sessions == []


def test_poll_when_priority_labels(agent, io_mocks, registry, mon_project, rate_limit_gate):
    """優先度ソート順の処理を確認する（正常系）。"""
    # 準備
    targets = [
        _issue(35, labels=["確認:intake-issue-triager", "優先度:いつでも"]),
        _issue(36, labels=["確認:intake-issue-triager", "優先度:急ぎ"]),
    ]
    # 実行
    service.poll(mon_project, agent, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE, priority_urgent="優先度:急ぎ", priority_low="優先度:いつでも", gate=rate_limit_gate)
    # 検証
    sent_sessions = [c.args[0] for c in io_mocks.send_keys.call_args_list]
    assert sent_sessions == [
        "ai-monitor-sandbox-36-intake-issue-triager",
        "ai-monitor-sandbox-35-intake-issue-triager",
    ]


def test_poll_when_phases_unregistered(io_mocks, registry, mon_project, rate_limit_gate):
    """フェーズ設定に無いエージェントの見送りを確認する（正常系）。"""
    # 準備
    unregistered = Agent(
        name="tester",
        confirm_label="確認:tester",
        processing_label="処理中:tester",
        model="sonnet",
        effort="high",
    )
    targets = [_issue(35, labels=["確認:tester"])]
    # 実行
    service.poll(mon_project, unregistered, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE, priority_urgent="優先度:急ぎ", priority_low="優先度:いつでも", gate=rate_limit_gate)
    # 検証: 副作用を起こさずに周期を終える
    io_mocks.create_session.assert_not_called()
    io_mocks.add_label.assert_not_called()
    io_mocks.send_keys.assert_not_called()


def test_poll_when_phases_unregistered_and_no_target(io_mocks, registry, mon_project, rate_limit_gate):
    """条件一致の対象が無い未登録エージェントでフェーズ設定を読まないことを確認する（正常系）。"""
    # 準備
    unregistered = Agent(
        name="tester",
        confirm_label="確認:tester",
        processing_label="処理中:tester",
        model="sonnet",
        effort="high",
    )
    targets = [_issue(35, labels=["確認:tester"], assignees=["shuhei1101"])]
    # 実行
    service.poll(mon_project, unregistered, targets, registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE, priority_urgent="優先度:急ぎ", priority_low="優先度:いつでも", gate=rate_limit_gate)
    # 検証: 毎周期のログ出力を避けるため設定の読み込み自体を行わない
    io_mocks.load_phase_config.assert_not_called()


def test_build_launch_prompt(agent):
    """起動プロンプトの組み立てを確認する（正常系）。"""
    # 実行
    prompt = service.build_launch_prompt(agent, 52, "Issue #52 [open]")
    # 検証: エージェント名・対象番号・スナップショットが含まれ、手順書は含まれない
    assert "intake-issue-triager" in prompt
    assert "- 対象番号: 52" in prompt
    assert "Issue #52 [open]" in prompt
    assert "# 初期処理" not in prompt


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
    assert "claude --model opus --effort xhigh --dangerously-skip-permissions" in sent_text
    assert "--append-system-prompt-file " in sent_text


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
    assert "claude --model opus --effort xhigh " in io_mocks.send_keys.call_args.args[1]
    # 起動プロンプトは一時ファイル経由で渡す（数万文字を send-keys の引数に直接埋めない）
    assert '"$(cat ' in io_mocks.send_keys.call_args.args[1]


def test_process_one_when_resumed(agent, io_mocks, registry, mon_project):
    """再開送信で生存時刻が更新されることを確認する（正常系）。"""
    # 準備: 待機で last_seen_at が古くなった既存セッション
    stale = (datetime.now(timezone.utc) - timedelta(minutes=45)).astimezone().isoformat()
    registry.register(
        AgentSession(
            session_name="ai-monitor-sandbox-35-intake-issue-triager",
            project="sandbox",
            agent_name="intake-issue-triager",
            primary_number=35,
            last_seen_at=stale,
        )
    )
    target = _issue(35, labels=["確認:intake-issue-triager"])
    # 実行
    service._process_one(
        mon_project, agent, target, open_targets=[target], registry=registry, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE
    )
    # 検証: 送信後に生存時刻が現在時刻へ進む（同じ周期のタイムアウト回収に kill されない）
    session = registry.find("sandbox", "intake-issue-triager", 35)
    assert session.last_seen_at != stale
    elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(session.last_seen_at)
    assert elapsed < timedelta(minutes=1)


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
    ranks = {"優先度:急ぎ": 0, "優先度:いつでも": 2}
    # 実行・検証
    assert service._sort_key(first, ranks) == (1, 35)
    assert service._sort_key(first, ranks) < service._sort_key(second, ranks)


def test_build_context_snapshot():
    """base 連鎖での配下のぶら下げを確認する（正常系）。"""
    # 準備: subsystem PR の下に成果物 PR と PoC PR、無関係の epic PR を混ぜる
    subsystem = _pr(50, base="feat/story/x/y", head="feat/be/x/y", labels=["layer:subsystem"])
    interface = _pr(52, base="feat/be/x/y", head="docs/be/x/y/interface", labels=["確認:architect"])
    poc = _pr(60, base="feat/be/x/y", head="poc/be/x/y/lib", labels=["確認:library-poc-runner"])
    other = _pr(99, base="master", head="feat/epic/z")
    # 実行
    snapshot = service.build_context_snapshot(subsystem, [subsystem, interface, poc, other])
    # 検証
    assert "#50" in snapshot and "#52" in snapshot and "#60" in snapshot
    assert "#99" not in snapshot
    assert "確認:architect" in snapshot
    assert "[open]" in snapshot


def test_build_context_snapshot_when_child_target():
    """子 PR 起点で最上位まで遡ることを確認する（正常系）。"""
    # 準備: 成果物 PR を起点にし、base で繋がる親 PR と兄弟を open 一覧に含める
    subsystem = _pr(50, base="master", head="feat/be/x/y", labels=["layer:subsystem"])
    interface = _pr(52, base="feat/be/x/y", head="docs/be/x/y/interface", labels=["確認:architect"])
    sibling = _pr(60, base="feat/be/x/y", head="poc/be/x/y/lib")
    open_targets = [subsystem, interface, sibling]
    # 実行
    from_child = service.build_context_snapshot(interface, open_targets)
    from_root = service.build_context_snapshot(subsystem, open_targets)
    # 検証: 親を基準に組み直されるので最上位起点と同じツリーになる
    assert from_child == from_root


def test_build_context_snapshot_when_parent_not_open():
    """親 PR が open 一覧に無い場合を確認する（正常系）。"""
    # 準備: base を head に持つ PR が open 一覧に居ない
    interface = _pr(52, base="feat/be/x/y", head="docs/be/x/y/interface", labels=["確認:architect"])
    # 実行
    snapshot = service.build_context_snapshot(interface, [interface])
    # 検証: 遡れないので対象自身が基準になる
    assert "#52" in snapshot
    assert "#50" not in snapshot


def test_build_context_snapshot_when_issue_target():
    """Issue 起点は対象 1 行だけになることを確認する（正常系）。"""
    # 準備: intake Issue は base 連鎖を持たない
    intake = _issue(30, labels=["layer:intake"])
    epic = _pr(35, base="master", head="feat/epic/x", linked=[30])
    # 実行
    snapshot = service.build_context_snapshot(intake, [intake, epic])
    # 検証
    assert snapshot == "intake #30 [open] labels=['layer:intake'] assignees=[]"


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


def test_build_launch_command(agent, io_mocks, mon_project):
    """起動コマンドの組み立てを確認する（正常系）。"""
    # 実行
    command = service.build_launch_command(
        "ai-monitor-sandbox-52-intake-issue-triager",
        agent,
        52,
        mon_project,
        "Issue #52 [open]",
        telemetry=None,
        port=8765,
        ai_monitor_wiki_base=WIKI_BASE,
    )
    # 検証: 環境変数で始まり、手順書は追記システムプロンプトのファイル・起動プロンプトはコマンド置換で渡す
    assert command.startswith("AI_MONITOR_PROJECT=sandbox AI_MONITOR_AGENT=intake-issue-triager")
    assert "claude --model opus --effort xhigh --dangerously-skip-permissions" in command
    assert "--append-system-prompt-file " in command
    assert '"$(cat ' in command
    docs_path = Path(tempfile.gettempdir()) / "ai-monitor-sandbox-52-intake-issue-triager.docs"
    assert str(docs_path) in command
    assert "# 初期処理" in docs_path.read_text(encoding="utf-8")


def test_build_launch_command_when_docs_exceed_arg_limit(agent, io_mocks, mon_project, monkeypatch):
    """手順書が 1 引数の上限を超えても起動コマンドに埋め込まれないことを確認する（正常系）。"""
    # 準備: 128 KiB を超えるエージェントドキュメントを返させる
    huge = "あ" * 200_000
    monkeypatch.setattr(service, "build_agent_docs", lambda *a, **k: huge)
    # 実行
    command = service.build_launch_command(
        "ai-monitor-sandbox-52-intake-issue-triager", agent, 52, mon_project, "Issue #52 [open]",
        telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE,
    )
    # 検証: コマンド長は上限未満で、本文はファイル側にある
    assert len(command.encode()) < 131072
    assert huge not in command
    docs_path = Path(tempfile.gettempdir()) / "ai-monitor-sandbox-52-intake-issue-triager.docs"
    assert docs_path.read_text(encoding="utf-8") == huge


def test_build_launch_command_when_mcp_config(agent, io_mocks, mon_project):
    """MCP 接続先がシェル引用付きで起動コマンドに載ることを確認する（正常系）。"""
    # 実行
    command = service.build_launch_command(
        "ai-monitor-sandbox-52-intake-issue-triager", agent, 52, mon_project, "Issue #52 [open]",
        telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE,
    )
    # 検証: シェル分解して取り出した引数が JSON として読め、待受ポートと対象プロジェクトが入る
    tokens = shlex.split(command)
    config = tokens[tokens.index("--mcp-config") + 1]
    server = json.loads(config)["mcpServers"]["ai-monitor-tools"]
    assert server["url"] == "http://localhost:8765/mcp"
    assert server["headers"]["X-Project"] == "sandbox"


def test_build_mcp_config(mon_project):
    """MCP 接続先の宣言の組み立てを確認する（正常系）。"""
    # 実行
    config = service.build_mcp_config(mon_project, 8765)
    # 検証: 接続方式・待受ポートの URL・対象プロジェクトのヘッダ・ツール確定待ちが入る
    server = json.loads(config)["mcpServers"]["ai-monitor-tools"]
    assert server["type"] == "http"
    assert server["url"] == "http://localhost:8765/mcp"
    assert server["headers"]["X-Project"] == "sandbox"
    assert server["alwaysLoad"] is True


def test_reset_session(agent, io_mocks, mon_project, monkeypatch):
    """セッションの作り直しを確認する（正常系）。"""
    # 準備
    order = []
    monkeypatch.setattr(service, "kill_session", lambda name: order.append(("kill", name)))
    monkeypatch.setattr(service, "create_session", lambda name, cwd: order.append(("create", name)))
    monkeypatch.setattr(service, "send_keys", lambda name, text: order.append(("send", name, text)))
    session = AgentSession(
        session_name="ai-monitor-sandbox-52-intake-issue-triager",
        project="sandbox",
        agent_name="intake-issue-triager",
        primary_number=52,
    )
    # 実行
    service.reset_session(
        session, mon_project, agent, telemetry=None, port=8765, ai_monitor_wiki_base=WIKI_BASE
    )
    # 検証: kill → 同名で create → 起動コマンドの送信の順
    assert [step[0] for step in order] == ["kill", "create", "send"]
    assert {step[1] for step in order} == {session.session_name}
    assert "claude --model opus" in order[2][2]
