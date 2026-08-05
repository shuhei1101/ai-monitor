"""「intake自動クローズ」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.main import build_agents, run_cycle
from ai_monitor.shared.types import Issue, PullRequest

FUTURE = "2100-01-01T00:00:00+00:00"


def _resp(items):
    r = MagicMock()
    r.parsed_data = items
    return r


def _intake_ns(number):
    return NS(
        number=number,
        state="open",
        labels=[NS(name="layer:intake")],
        assignees=[NS(login="shuhei1101")],
        body="",
        pull_request=None,
    )


def _pr_ns(number, issue_number):
    return NS(
        number=number,
        state="open",
        draft=True,
        labels=[NS(name="layer:epic")],
        assignees=[NS(login="shuhei1101")],
        body=f"## 紐づく Issue\n\n- #{issue_number}\n",
        pull_request=NS(url=f"http://p/{number}"),
        base=NS(ref="master"),
    )


def _prev_pr(number, issue_number):
    return PullRequest(
        number=number,
        state="open",
        labels=["layer:epic"],
        assignees=[],
        linked_issue_numbers=[issue_number],
        base_ref="master",
        head_ref=f"feat/epic/x{number}",
    )


def _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, notify):
    agents = build_agents(label_settings, agent_settings=agent_settings)
    return run_cycle(mon_settings, agents, registry=mon_registry, prev_targets=prev, last_heartbeat_at=FUTURE, labels=label_settings, gate=RateLimitGate(), notified_gates={}, notify=notify)


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, notify):
    """紐づく PR が全て一覧から消えた intake のクローズを確認する（正常系）。"""
    # 準備: 前周期には紐づく PR が 2 件、今周期は 0 件
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([_intake_ns(30)])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    prev = {
        "sandbox": [
            Issue(number=30, state="open", labels=["layer:intake"]),
            _prev_pr(35, 30),
            _prev_pr(36, 30),
        ]
    }
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, notify)
    # 検証
    kwargs = gh_mon.rest.issues.update.call_args.kwargs
    assert kwargs["issue_number"] == 30
    assert kwargs["state"] == "closed"
    assert kwargs["state_reason"] == "completed"


def test_normal_when_pr_open(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, notify):
    """未マージの PR が残る場合の見送りを確認する（正常系）。"""
    # 準備: 今周期にも紐づく PR が 1 件 open で残る
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([_intake_ns(30), _pr_ns(36, 30)])]
    gh_mon.rest.pulls.list.side_effect = [_resp([NS(number=36, base=NS(ref="master"), head=NS(ref="feat/epic/x36"))])]
    prev = {
        "sandbox": [
            Issue(number=30, state="open", labels=["layer:intake"]),
            _prev_pr(35, 30),
            _prev_pr(36, 30),
        ]
    }
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, notify)
    # 検証
    gh_mon.rest.issues.update.assert_not_called()


def test_error_when_api_error(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, request_failed, notify):
    """クローズ失敗で周期を見送ることを確認する（異常系）。"""
    # 準備
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([_intake_ns(30)])]
    gh_mon.rest.pulls.list.side_effect = [_resp([])]
    gh_mon.rest.issues.update.side_effect = request_failed(500)
    prev = {"sandbox": [Issue(number=30, state="open", labels=["layer:intake"]), _prev_pr(35, 30)]}
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, prev, notify)
    # 検証: 例外が伝播しない（プロセス継続 = ここに到達する）
    assert gh_mon.rest.issues.update.called
