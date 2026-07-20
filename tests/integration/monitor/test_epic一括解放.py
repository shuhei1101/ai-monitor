"""「epic一括解放」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.main import build_agents, run_cycle
from ai_monitor.shared.types import Issue

FUTURE = "2100-01-01T00:00:00+00:00"


def _resp(data):
    r = MagicMock()
    r.parsed_data = data
    return r


def _closed_epic_ns(number):
    return NS(
        number=number,
        state="closed",
        labels=[NS(name="layer:epic")],
        assignees=[],
        body="",
        pull_request=None,
        sub_issues_summary=None,
    )


def _register_family(mon_registry):
    for number, agent in [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")]:
        mon_registry.register(
            AgentSession(
                session_name=f"ai-monitor-sandbox-{number}-{agent}",
                project="sandbox",
                agent_name=agent,
                primary_number=number,
            )
        )


def _prev_targets():
    return {"sandbox": [Issue(number=35, state="open", labels=["layer:epic"])]}


def _cycle(mon_settings, label_settings, mon_registry, prev, current_items):
    agents = build_agents(label_settings)
    return run_cycle(
        mon_settings, agents, registry=mon_registry, prev_targets=prev, last_heartbeat_at=FUTURE
    )


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, mon_registry):
    """epic close 検知 → 配下の全セッション解放を確認する（正常系）。"""
    # 準備
    _register_family(mon_registry)
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.issues.get.return_value = _resp(_closed_epic_ns(35))
    gh_mon.rest.issues.list_sub_issues.side_effect = lambda **kwargs: _resp(
        {35: [NS(number=40)], 40: []}[kwargs["issue_number"]]
    )
    gh_mon.rest.issues.get_parent.return_value = _resp(NS(number=30))
    # 実行
    _cycle(mon_settings, label_settings, mon_registry, _prev_targets(), [])
    # 検証
    assert mon_registry.sessions == []
    killed = [c[2] for c in tmux_calls.calls if c[0] == "kill-session"]
    assert sorted(killed) == [
        "ai-monitor-sandbox-30-intake-issue-triager",
        "ai-monitor-sandbox-35-epic-conductor",
        "ai-monitor-sandbox-40-story-conductor",
    ]


def test_normal_when_confirm_remains(gh_mon, tmux_calls, mon_settings, label_settings, mon_registry):
    """確認ラベル残存の解放見送りを確認する（正常系）。"""
    # 準備
    _register_family(mon_registry)
    remaining = NS(
        number=40,
        state="open",
        labels=[NS(name="layer:subsystem"), NS(name="確認:subsystem-conductor"), NS(name="処理中:subsystem-conductor")],
        assignees=[],
        body="",
        pull_request=None,
        sub_issues_summary=None,
    )
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([remaining])]
    gh_mon.rest.issues.get.return_value = _resp(_closed_epic_ns(35))
    gh_mon.rest.issues.list_sub_issues.side_effect = lambda **kwargs: _resp(
        {35: [NS(number=40)], 40: []}[kwargs["issue_number"]]
    )
    gh_mon.rest.issues.get_parent.return_value = _resp(NS(number=30))
    # 実行
    _cycle(mon_settings, label_settings, mon_registry, _prev_targets(), [])
    # 検証
    assert len(mon_registry.sessions) == 3
    assert not any(c[0] == "kill-session" for c in tmux_calls.calls)


def test_error_when_api_error(gh_mon, tmux_calls, mon_settings, label_settings, mon_registry, request_failed):
    """単体取得の失敗で周期を見送ることを確認する（異常系）。"""
    # 準備
    _register_family(mon_registry)
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.issues.get.side_effect = request_failed(500)
    # 実行
    _cycle(mon_settings, label_settings, mon_registry, _prev_targets(), [])
    # 検証
    assert len(mon_registry.sessions) == 3
    assert not any(c[0] == "kill-session" for c in tmux_calls.calls)
