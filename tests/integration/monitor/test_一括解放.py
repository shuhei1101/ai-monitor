"""「一括解放」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.main import build_agents, run_cycle
from ai_monitor.shared.types import Issue

FUTURE = "2100-01-01T00:00:00+00:00"


def _resp(data):
    r = MagicMock()
    r.parsed_data = data
    return r


def _issue_ns(number, layer, state="closed", extra_labels=()):
    return NS(
        number=number,
        state=state,
        labels=[NS(name=layer), *(NS(name=n) for n in extra_labels)],
        assignees=[],
        body="",
        pull_request=None,
        sub_issues_summary=None,
    )


def _register(mon_registry, pairs):
    for number, agent in pairs:
        mon_registry.register(
            AgentSession(
                session_name=f"ai-monitor-sandbox-{number}-{agent}",
                project="sandbox",
                agent_name=agent,
                primary_number=number,
            )
        )


def _wire(gh_mon, *, closed, tree, parents, issues=None):
    """単体取得 / Sub-issue ツリー / 親取得の応答を配線する。"""
    known = {closed.number: closed, **(issues or {})}
    gh_mon.rest.issues.get.side_effect = lambda **kw: _resp(known[kw["issue_number"]])
    gh_mon.rest.issues.list_sub_issues.side_effect = lambda **kw: _resp(
        [NS(number=n) for n in tree.get(kw["issue_number"], [])]
    )

    def _parent(**kw):
        number = parents.get(kw["issue_number"])
        if number is None:
            raise _not_found()
        return _resp(NS(number=number))

    gh_mon.rest.issues.get_parent.side_effect = _parent


def _not_found():
    from githubkit.exception import RequestFailed

    response = MagicMock()
    response.status_code = 404
    return RequestFailed(response)


def _cycle(mon_settings, label_settings, agent_models, mon_registry, prev, current, notify):
    agents = build_agents(label_settings, agent_models=agent_models)
    return run_cycle(
        mon_settings,
        agents,
        registry=mon_registry,
        prev_targets=prev,
        last_heartbeat_at=FUTURE,
        labels=label_settings,
        gate=RateLimitGate(),
     notify=notify)


def _killed(tmux_calls):
    return sorted(c[2] for c in tmux_calls.calls if c[0] == "kill-session")


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, notify):
    """最上位 close 検知 → 配下の全セッション解放を確認する（正常系）。"""
    # 準備: 親が intake の epic #35 が closed
    _register(mon_registry, [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    _wire(
        gh_mon,
        closed=_issue_ns(35, "layer:epic"),
        tree={35: [40], 40: []},
        parents={35: 30},
        issues={30: _issue_ns(30, "layer:intake", state="open")},
    )
    prev = {"sandbox": [Issue(number=35, state="open", labels=["layer:epic"])]}
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, prev, [], notify)
    # 検証
    assert mon_registry.sessions == []
    assert _killed(tmux_calls) == [
        "ai-monitor-sandbox-30-intake-issue-triager",
        "ai-monitor-sandbox-35-epic-conductor",
        "ai-monitor-sandbox-40-story-conductor",
    ]


def test_normal_when_system_is_top(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, notify):
    """system が最上位のときの 4 レイヤー一括解放を確認する（正常系）。"""
    # 準備: 親を持たない system #10 が closed
    _register(
        mon_registry,
        [(10, "system-conductor"), (35, "epic-conductor"), (40, "story-conductor"), (50, "subsystem-conductor")],
    )
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    _wire(gh_mon, closed=_issue_ns(10, "layer:system"), tree={10: [35], 35: [40], 40: [50], 50: []}, parents={})
    prev = {"sandbox": [Issue(number=10, state="open", labels=["layer:system"])]}
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, prev, [], notify)
    # 検証
    assert mon_registry.sessions == []
    assert _killed(tmux_calls) == [
        "ai-monitor-sandbox-10-system-conductor",
        "ai-monitor-sandbox-35-epic-conductor",
        "ai-monitor-sandbox-40-story-conductor",
        "ai-monitor-sandbox-50-subsystem-conductor",
    ]


def test_normal_when_story_is_top(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, notify):
    """story が最上位のときの解放を確認する（正常系）。"""
    # 準備: 親を持たない story #40 が closed
    _register(mon_registry, [(40, "story-conductor"), (50, "subsystem-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    _wire(gh_mon, closed=_issue_ns(40, "layer:story"), tree={40: [50], 50: []}, parents={})
    prev = {"sandbox": [Issue(number=40, state="open", labels=["layer:story"])]}
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, prev, [], notify)
    # 検証
    assert mon_registry.sessions == []
    assert _killed(tmux_calls) == [
        "ai-monitor-sandbox-40-story-conductor",
        "ai-monitor-sandbox-50-subsystem-conductor",
    ]


def test_normal_when_subsystem_is_top(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, notify):
    """subsystem が最上位（配下なし）のときの解放を確認する（正常系）。"""
    # 準備: 親も子も持たない subsystem #50 が closed
    _register(mon_registry, [(50, "subsystem-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    _wire(gh_mon, closed=_issue_ns(50, "layer:subsystem"), tree={50: []}, parents={})
    prev = {"sandbox": [Issue(number=50, state="open", labels=["layer:subsystem"])]}
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, prev, [], notify)
    # 検証
    assert mon_registry.sessions == []
    assert _killed(tmux_calls) == ["ai-monitor-sandbox-50-subsystem-conductor"]


def test_normal_when_parent_remains(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, notify):
    """親を持つ Issue の close で解放しないことを確認する（正常系）。"""
    # 準備: 親が open の system である epic #35 が closed
    _register(mon_registry, [(10, "system-conductor"), (35, "epic-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    _wire(
        gh_mon,
        closed=_issue_ns(35, "layer:epic"),
        tree={35: []},
        parents={35: 10},
        issues={10: _issue_ns(10, "layer:system", state="open")},
    )
    prev = {"sandbox": [Issue(number=35, state="open", labels=["layer:epic"])]}
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, prev, [], notify)
    # 検証
    assert len(mon_registry.sessions) == 2
    assert _killed(tmux_calls) == []


def test_normal_when_confirm_remains(gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, notify):
    """確認ラベル残存の解放見送りを確認する（正常系）。"""
    # 準備: 配下 subsystem #40 に 確認:* が残っている
    _register(mon_registry, [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")])
    remaining = _issue_ns(
        40,
        "layer:subsystem",
        state="open",
        # 処理中 も付けて、本周期で新規セッションが起動しない状態にする
        extra_labels=["確認:subsystem-conductor", "処理中:subsystem-conductor"],
    )
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([remaining])]
    _wire(
        gh_mon,
        closed=_issue_ns(35, "layer:epic"),
        tree={35: [40], 40: []},
        parents={35: 30},
        issues={30: _issue_ns(30, "layer:intake", state="open")},
    )
    prev = {"sandbox": [Issue(number=35, state="open", labels=["layer:epic"])]}
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, prev, [], notify)
    # 検証
    assert len(mon_registry.sessions) == 3
    assert _killed(tmux_calls) == []


def test_error_when_api_error(
    gh_mon, tmux_calls, mon_settings, label_settings, agent_models, mon_registry, request_failed,
notify):
    """単体取得の失敗で周期を見送ることを確認する（異常系）。"""
    # 準備
    _register(mon_registry, [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.issues.get.side_effect = request_failed(500)
    prev = {"sandbox": [Issue(number=35, state="open", labels=["layer:epic"])]}
    # 実行
    _cycle(mon_settings, label_settings, agent_models, mon_registry, prev, [], notify)
    # 検証
    assert len(mon_registry.sessions) == 3
    assert _killed(tmux_calls) == []
