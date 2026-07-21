"""「タイムアウト検知」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.main import build_agents, run_cycle

PAST = "2000-01-01T00:00:00+00:00"


def _resp(data):
    r = MagicMock()
    r.parsed_data = data
    return r


def _target_ns(number, labels):
    return NS(
        number=number,
        state="open",
        labels=[NS(name=name) for name in labels],
        assignees=[NS(login="shuhei1101")],
        body="",
        pull_request=None,
        sub_issues_summary=None,
    )


def _register_timed_out(mon_registry):
    mon_registry.register(
        AgentSession(
            session_name="ai-monitor-sandbox-52-architect",
            project="sandbox",
            agent_name="architect",
            primary_number=52,
            last_seen_at=PAST,
        )
    )


def _cycle(mon_settings, label_settings, agent_models, mon_registry):
    agents = build_agents(label_settings, agent_models=agent_models)
    return run_cycle(mon_settings, agents, registry=mon_registry, prev_targets={}, last_heartbeat_at=PAST)


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """超過セッションの kill + ラベル除去 + 台帳除去を確認する（正常系）。"""
    # 準備
    _register_timed_out(mon_registry)
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_target_ns(52, ["確認:architect", "処理中:architect"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert gh_mon.rest.issues.remove_label.call_args.kwargs["name"] == "処理中:architect"
    assert ["kill-session", "-t", "ai-monitor-sandbox-52-architect"] in tmux_calls.calls
    assert mon_registry.sessions == []


def test_normal_when_waiting(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """待機中セッションの対象外を確認する（正常系）。"""
    # 準備
    _register_timed_out(mon_registry)
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([_target_ns(52, ["議論中"])])]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    gh_mon.rest.issues.remove_label.assert_not_called()
    assert not any(c[0] == "kill-session" for c in tmux_calls.calls)
    assert len(mon_registry.sessions) == 1


def test_normal_when_session_gone(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """tmux 実体消失の台帳修復を確認する（正常系）。"""
    # 準備
    _register_timed_out(mon_registry)
    tmux_calls.has_session_rc = 1
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert mon_registry.sessions == []
    assert not any(c[0] == "kill-session" for c in tmux_calls.calls)


def test_error_when_api_error(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, request_failed):
    """ラベル除去失敗の見送りを確認する（異常系）。"""
    # 準備
    _register_timed_out(mon_registry)
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_target_ns(52, ["確認:architect", "処理中:architect"])])
    ]
    gh_mon.rest.issues.remove_label.side_effect = request_failed(500)
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert not any(c[0] == "kill-session" for c in tmux_calls.calls)
    assert len(mon_registry.sessions) == 1
