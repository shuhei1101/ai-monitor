"""「一括解放」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.main import build_agents, run_cycle
from ai_monitor.shared.types import Issue, PullRequest

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
    )


def _pr(number, layer, base, head, linked=(), extra_labels=()):
    return PullRequest(
        number=number,
        state="open",
        labels=[layer, *extra_labels],
        assignees=[],
        linked_issue_numbers=list(linked),
        base_ref=base,
        head_ref=head,
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


def _wire(gh_mon, *, closed, issues=None):
    """単体取得の応答を配線する（配下の収集は前周期一覧の base 連鎖で完結する）。"""
    known = {closed.number: closed, **(issues or {})}
    gh_mon.rest.issues.get.side_effect = lambda **kw: _resp(known[kw["issue_number"]])


def _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, current, notify):
    agents = build_agents(label_settings, agent_settings=agent_settings)
    return run_cycle(
        mon_settings,
        agents,
        registry=mon_registry,
        prev_targets=prev,
        last_heartbeat_at=FUTURE,
        labels=label_settings,
        gate=RateLimitGate(),
        notified_gates={},
     notify=notify)


def _killed(tmux_calls):
    return sorted(c[2] for c in tmux_calls.calls if c[0] == "kill-session")


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, notify):
    """最上位 close 検知 → 配下の全セッション解放を確認する（正常系）。"""
    # 準備: base が master の epic PR #35（起点 Issue #30）が closed
    _register(mon_registry, [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    _wire(gh_mon, closed=_issue_ns(35, "layer:epic"))
    prev = {
        "sandbox": [
            _pr(35, "layer:epic", "master", "feat/epic/x", linked=[30]),
            _pr(40, "layer:story", "feat/epic/x", "feat/story/x/y"),
        ]
    }
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, [], notify)
    # 検証
    assert mon_registry.sessions == []
    assert _killed(tmux_calls) == [
        "ai-monitor-sandbox-30-intake-issue-triager",
        "ai-monitor-sandbox-35-epic-conductor",
        "ai-monitor-sandbox-40-story-conductor",
    ]


def test_normal_when_system_is_top(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, notify):
    """system が最上位のときの 4 レイヤー一括解放を確認する（正常系）。"""
    # 準備: base が master の system PR #10 が closed
    _register(
        mon_registry,
        [(10, "system-conductor"), (35, "epic-conductor"), (40, "story-conductor"), (50, "subsystem-conductor")],
    )
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    _wire(gh_mon, closed=_issue_ns(10, "layer:system"))
    prev = {
        "sandbox": [
            _pr(10, "layer:system", "master", "docs/system/x"),
            _pr(35, "layer:epic", "docs/system/x", "feat/epic/x"),
            _pr(40, "layer:story", "feat/epic/x", "feat/story/x/y"),
            _pr(50, "layer:subsystem", "feat/story/x/y", "feat/be/x/y"),
        ]
    }
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, [], notify)
    # 検証
    assert mon_registry.sessions == []
    assert _killed(tmux_calls) == [
        "ai-monitor-sandbox-10-system-conductor",
        "ai-monitor-sandbox-35-epic-conductor",
        "ai-monitor-sandbox-40-story-conductor",
        "ai-monitor-sandbox-50-subsystem-conductor",
    ]


def test_normal_when_story_is_top(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, notify):
    """story が最上位のときの解放を確認する（正常系）。"""
    # 準備: base が master の story PR #40 が closed
    _register(mon_registry, [(40, "story-conductor"), (50, "subsystem-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    _wire(gh_mon, closed=_issue_ns(40, "layer:story"))
    prev = {
        "sandbox": [
            _pr(40, "layer:story", "master", "feat/story/x/y"),
            _pr(50, "layer:subsystem", "feat/story/x/y", "feat/be/x/y"),
        ]
    }
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, [], notify)
    # 検証
    assert mon_registry.sessions == []
    assert _killed(tmux_calls) == [
        "ai-monitor-sandbox-40-story-conductor",
        "ai-monitor-sandbox-50-subsystem-conductor",
    ]


def test_normal_when_subsystem_is_top(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, notify):
    """subsystem が最上位（配下なし）のときの解放を確認する（正常系）。"""
    # 準備: base が master で配下を持たない subsystem PR #50 が closed
    _register(mon_registry, [(50, "subsystem-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    _wire(gh_mon, closed=_issue_ns(50, "layer:subsystem"))
    prev = {"sandbox": [_pr(50, "layer:subsystem", "master", "feat/be/x/y")]}
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, [], notify)
    # 検証
    assert mon_registry.sessions == []
    assert _killed(tmux_calls) == ["ai-monitor-sandbox-50-subsystem-conductor"]


def test_normal_when_parent_remains(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, notify):
    """base が親レイヤーの PR の close で解放しないことを確認する（正常系）。"""
    # 準備: base が system ブランチの epic PR #35 が closed
    _register(mon_registry, [(10, "system-conductor"), (35, "epic-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    _wire(
        gh_mon,
        closed=_issue_ns(35, "layer:epic"),
        issues={10: _issue_ns(10, "layer:system", state="open")},
    )
    prev = {
        "sandbox": [
            _pr(10, "layer:system", "master", "docs/system/x"),
            _pr(35, "layer:epic", "docs/system/x", "feat/epic/x"),
        ]
    }
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, [], notify)
    # 検証: 一括解放は発火せず、上位の system セッションは残る
    # （closed の epic 自身のセッションは個別解放が拾うため対象外）
    assert [s.primary_number for s in mon_registry.sessions] == [10]
    assert _killed(tmux_calls) == ["ai-monitor-sandbox-35-epic-conductor"]
    assert notify.calls == []


def test_normal_when_confirm_remains(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, notify):
    """確認ラベル残存の解放見送りを確認する（正常系）。"""
    # 準備: 配下の subsystem PR #40 に 確認:* が残っている
    _register(mon_registry, [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")])
    remaining = _issue_ns(
        40,
        "layer:subsystem",
        state="open",
        # 処理中 も付けて、本周期で新規セッションが起動しない状態にする
        extra_labels=["確認:subsystem-conductor", "処理中:subsystem-conductor"],
    )
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([remaining])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    _wire(
        gh_mon,
        closed=_issue_ns(35, "layer:epic"),
        issues={30: _issue_ns(30, "layer:intake", state="open")},
    )
    prev = {
        "sandbox": [
            _pr(35, "layer:epic", "master", "feat/epic/x", linked=[30]),
            _pr(40, "layer:subsystem", "feat/epic/x", "feat/be/x/y"),
        ]
    }
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, [], notify)
    # 検証: 一括解放は発火せず、intake と配下 subsystem のセッションは残る
    # （closed の epic 自身のセッションは個別解放が拾うため対象外）
    assert sorted(s.primary_number for s in mon_registry.sessions) == [30, 40]
    assert _killed(tmux_calls) == ["ai-monitor-sandbox-35-epic-conductor"]
    assert notify.calls == []


def test_error_when_api_error(
    gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, request_failed,
notify):
    """単体取得の失敗で周期を見送ることを確認する（異常系）。"""
    # 準備
    _register(mon_registry, [(30, "intake-issue-triager"), (35, "epic-conductor"), (40, "story-conductor")])
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    gh_mon.rest.issues.get.side_effect = request_failed(500)
    prev = {"sandbox": [Issue(number=35, state="open", labels=["layer:epic"])]}
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, [], notify)
    # 検証: 単体取得の失敗で周期を見送るため、セッションは全て残る
    assert len(mon_registry.sessions) == 3
    assert _killed(tmux_calls) == []
    assert notify.calls == []
