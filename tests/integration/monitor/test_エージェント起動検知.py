"""「エージェント起動検知」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.main import build_agents, run_cycle

FUTURE = "2100-01-01T00:00:00+00:00"


def _resp(items):
    r = MagicMock()
    r.parsed_data = items
    return r


def _issue_ns(number, labels, assignees=()):
    return NS(
        number=number,
        state="open",
        labels=[NS(name=name) for name in labels],
        assignees=[NS(login=login) for login in assignees],
        body="",
        pull_request=None,
        sub_issues_summary=None,
    )


def _cycle(mon_settings, label_settings, agent_models, mon_registry, prev=None):
    agents = build_agents(label_settings, agent_models=agent_models)
    return run_cycle(
        mon_settings, agents, registry=mon_registry, prev_targets=prev or {}, last_heartbeat_at=FUTURE
    )


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, tmp_state_path):
    """新規対象の検知 → セッション作成 + skill 起動を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_issue_ns(35, ["確認:intake-issue-triager"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    session_name = "ai-monitor-sandbox-35-intake-issue-triager"
    assert ["new-session", "-d", "-s", session_name, "-c", "/tmp/sandbox"] in tmux_calls.calls
    assert mon_registry.find("sandbox", "intake-issue-triager", 35) is not None
    assert tmp_state_path.exists()
    assert gh_mon.rest.issues.add_labels.call_args.kwargs["labels"] == ["処理中:intake-issue-triager"]
    send = next(c for c in tmux_calls.calls if c[0] == "send-keys")
    assert send[3].startswith(
        'claude --model sonnet --dangerously-skip-permissions "/ai-monitor:intake-issue-triager 35'
    )
    assert "#35" in send[3]


def test_normal_when_existing_session(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """既存セッションへの再開送信を確認する（正常系）。"""
    # 準備
    mon_registry.register(
        AgentSession(
            session_name="ai-monitor-sandbox-35-intake-issue-triager",
            project="sandbox",
            agent_name="intake-issue-triager",
            primary_number=35,
        )
    )
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_issue_ns(35, ["確認:intake-issue-triager"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert not any(c[0] == "new-session" for c in tmux_calls.calls)
    send = next(c for c in tmux_calls.calls if c[0] == "send-keys")
    assert send[2] == "ai-monitor-sandbox-35-intake-issue-triager"
    assert send[3].startswith("状態が変化しました")


def test_normal_when_processing_label(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """処理中ラベル付きの対象の除外を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_issue_ns(35, ["確認:intake-issue-triager", "処理中:intake-issue-triager"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert tmux_calls.calls == []
    gh_mon.rest.issues.add_labels.assert_not_called()


def test_error_when_api_error(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, request_failed):
    """対象一覧の取得失敗で周期を見送ることを確認する（異常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = request_failed(500)
    # 実行
    targets_by_project, _ = _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert targets_by_project == {}
    assert tmux_calls.calls == []
