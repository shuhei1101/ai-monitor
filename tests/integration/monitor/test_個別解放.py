"""「個別解放」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.main import build_agents, run_cycle

FUTURE = "2100-01-01T00:00:00+00:00"


def _resp(data):
    r = MagicMock()
    r.parsed_data = data
    return r


def _poc_pr_ns(number, state):
    return NS(
        number=number,
        state=state,
        labels=[],
        assignees=[],
        body="",
        pull_request=None,
        sub_issues_summary=None,
    )


def _register_poc_session(mon_registry):
    mon_registry.register(
        AgentSession(
            session_name="ai-monitor-sandbox-60-library-poc-runner",
            project="sandbox",
            agent_name="library-poc-runner",
            primary_number=60,
        )
    )


def _cycle(mon_settings, label_settings, agent_models, mon_registry):
    agents = build_agents(label_settings, agent_models=agent_models)
    return run_cycle(mon_settings, agents, registry=mon_registry, prev_targets={}, last_heartbeat_at=FUTURE)


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """close 確認後のセッション解放を確認する（正常系）。"""
    # 準備
    _register_poc_session(mon_registry)
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.issues.get.return_value = _resp(_poc_pr_ns(60, state="closed"))
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert mon_registry.sessions == []
    assert ["kill-session", "-t", "ai-monitor-sandbox-60-library-poc-runner"] in tmux_calls.calls


def test_normal_when_still_open(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """open のままの見送りを確認する（正常系）。"""
    # 準備
    _register_poc_session(mon_registry)
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.issues.get.return_value = _resp(_poc_pr_ns(60, state="open"))
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert len(mon_registry.sessions) == 1
    assert not any(c[0] == "kill-session" for c in tmux_calls.calls)


def test_error_when_api_error(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, request_failed):
    """単体取得の失敗で周期を見送ることを確認する（異常系）。"""
    # 準備
    _register_poc_session(mon_registry)
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.issues.get.side_effect = request_failed(500)
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    assert len(mon_registry.sessions) == 1
    assert not any(c[0] == "kill-session" for c in tmux_calls.calls)
