"""「レートリミット再開」の結合テスト。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from ai_monitor.features.agents.service import RESUME_TEXT
from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.features.sessions.types import AgentSession
from ai_monitor.main import build_agents, run_cycle

PAST = "2000-01-01T00:00:00+00:00"
SESSION = "ai-monitor-sandbox-1069-epic-conductor"


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


@pytest.fixture
def blocked_session(mon_registry):
    """待機で生存時刻が古くなったセッションを台帳へ登録する。"""
    mon_registry.register(
        AgentSession(
            session_name=SESSION,
            project="sandbox",
            agent_name="epic-conductor",
            primary_number=1069,
            last_seen_at=PAST,
        )
    )


def _cycle(mon_settings, label_settings, agent_settings, mon_registry, gate, notify):
    agents = build_agents(label_settings, agent_settings=agent_settings)
    return run_cycle(
        mon_settings, agents, registry=mon_registry, prev_targets={}, last_heartbeat_at=PAST,
        labels=label_settings, gate=gate,
     notify=notify)


def test_normal(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, blocked_session, notify):
    """解除時刻の到達検知 → 応答と定型文の送信を確認する（正常系）。"""
    # 準備: 解除済みの関門と、回収条件を満たす処理中の対象
    gate = RateLimitGate()
    gate.block(SESSION, datetime.now(timezone.utc) - timedelta(minutes=1))
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_target_ns(1069, ["確認:epic-conductor", "処理中:epic-conductor"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, gate, notify)
    # 検証: Enter と再開の定型文がこの順に送られている
    sent = [c[3] for c in tmux_calls.calls if c[0] == "send-keys" and c[2] == SESSION]
    assert sent[: sent.index(RESUME_TEXT)].count("Enter") >= 1
    assert RESUME_TEXT in sent
    # 検証: kill されず、生存時刻が更新され、待機状態が消えている
    assert not any(c[0] == "kill-session" for c in tmux_calls.calls)
    assert mon_registry.sessions[0].last_seen_at != PAST
    assert gate.take_resumable(datetime.now(timezone.utc)) == []


def test_normal_when_blocked(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, blocked_session, notify):
    """解除時刻の前は何もしないことを確認する（正常系）。"""
    # 準備
    gate = RateLimitGate()
    gate.block(SESSION, datetime.now(timezone.utc) + timedelta(minutes=30))
    gh_mon.rest.issues.list_for_repo.side_effect = [
        _resp([_target_ns(1069, ["確認:epic-conductor", "処理中:epic-conductor"])])
    ]
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, gate, notify)
    # 検証: 送信が発生せず、待機状態が残っている
    assert not any(c[0] == "send-keys" for c in tmux_calls.calls)
    assert gate.is_blocked(datetime.now(timezone.utc)) is True
    assert mon_registry.sessions[0].last_seen_at == PAST


def test_normal_when_session_gone(gh_mon, tmux_calls, mon_settings, label_settings, agent_settings, mon_registry, blocked_session, notify):
    """tmux にセッションが無い対象の読み飛ばしを確認する（正常系）。"""
    # 準備: 解放済みセッション
    gate = RateLimitGate()
    gate.block(SESSION, datetime.now(timezone.utc) - timedelta(minutes=1))
    tmux_calls.has_session_rc = 1
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([])]
    # 実行
    _cycle(mon_settings, label_settings, agent_settings, mon_registry, gate, notify)
    # 検証: 送信も生存時刻の更新も行わず、待機状態は消えている
    assert not any(c[0] == "send-keys" for c in tmux_calls.calls)
    assert gate.is_blocked(datetime.now(timezone.utc)) is False
    assert gate.take_resumable(datetime.now(timezone.utc)) == []
