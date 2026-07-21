"""「intake自動クローズ」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from ai_monitor.main import build_agents, run_cycle

FUTURE = "2100-01-01T00:00:00+00:00"


def _resp(items):
    r = MagicMock()
    r.parsed_data = items
    return r


def _intake_ns(number, total, completed):
    return NS(
        number=number,
        state="open",
        labels=[NS(name="layer:intake")],
        assignees=[NS(login="shuhei1101")],
        body="",
        pull_request=None,
        sub_issues_summary=NS(total=total, completed=completed),
    )


def _cycle(mon_settings, label_settings, agent_models, mon_registry):
    agents = build_agents(label_settings, agent_models=agent_models)
    return run_cycle(mon_settings, agents, registry=mon_registry, prev_targets={}, last_heartbeat_at=FUTURE)


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """全 Sub-issue closed の intake クローズを確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([_intake_ns(30, total=2, completed=2)])]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    kwargs = gh_mon.rest.issues.update.call_args.kwargs
    assert kwargs["issue_number"] == 30
    assert kwargs["state"] == "closed"
    assert kwargs["state_reason"] == "completed"


def test_normal_when_incomplete(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry):
    """未完了の子ありの見送りを確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([_intake_ns(30, total=2, completed=1)])]
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証
    gh_mon.rest.issues.update.assert_not_called()


def test_error_when_api_error(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, request_failed):
    """クローズ失敗で周期を見送ることを確認する（異常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([_intake_ns(30, total=2, completed=2)])]
    gh_mon.rest.issues.update.side_effect = request_failed(500)
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry)
    # 検証: 例外が伝播しない（プロセス継続 = ここに到達する）
    assert gh_mon.rest.issues.update.called
