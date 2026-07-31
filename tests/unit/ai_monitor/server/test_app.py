"""`src/ai_monitor/server/app.py` の単体テスト。"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import ai_monitor.server.app as app_mod
from ai_monitor.features.agents.types import Agent

RESETS_AT = datetime(2026, 7, 29, 2, 30, tzinfo=timezone(timedelta(hours=9)))


@pytest.fixture
def agents() -> list[Agent]:
    return [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet", effort="high")]


@pytest.fixture
def client(mon_settings, mon_registry, agents, monkeypatch, label_settings):
    import ai_monitor.main as main_mod

    # lifespan が起動するポーリングループを空回しにする
    monkeypatch.setattr(main_mod, "run_cycle", lambda *args, **kwargs: ({}, "1970-01-01T00:00:00+00:00"))
    app = app_mod.create_app(mon_settings, registry=mon_registry, agents=agents, label_settings=label_settings)
    with TestClient(app, base_url="http://localhost:8765") as client:
        yield client


def test_create_app(client):
    """MCP のマウントを確認する（正常系）。"""
    # 実行
    response = client.post("/mcp", follow_redirects=False)
    # 検証
    assert response.status_code != 404


def test_create_app_when_unknown_path(client):
    """未知パスの 404 を確認する（正常系）。"""
    # 実行
    response = client.get("/unknown")
    # 検証
    assert response.status_code == 404


def test_receive_context_reset(client, mon_settings, session_factory, monkeypatch):
    """リセット要求の受理と /clear + 送信を確認する（正常系）。"""
    # 準備
    calls = []
    monkeypatch.setattr(app_mod, "reset_session", lambda s, p, a, **kw: calls.append((s, p, a, kw)))
    session = session_factory("architect", 170)
    # 実行
    response = client.post(
        "/context_reset",
        json={"project": "sandbox", "agent_name": "architect", "number": 170},
    )
    # 検証: 該当セッションのリセットが 1 回呼ばれ受理される
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(calls) == 1
    reset_target, reset_project, reset_agent, kwargs = calls[0]
    assert reset_target.session_name == session.session_name
    assert reset_project.name == "sandbox"
    assert reset_agent.name == "architect"
    assert kwargs["port"] == mon_settings.port


def test_receive_context_reset_when_session_missing(client, monkeypatch):
    """台帳に無いセッションからの要求を拒否する（異常系）。"""
    # 準備
    calls = []
    monkeypatch.setattr(app_mod, "reset_session", lambda s, p, a, **kw: calls.append(s))
    # 実行
    response = client.post(
        "/context_reset",
        json={"project": "sandbox", "agent_name": "architect", "number": 999},
    )
    # 検証
    assert response.status_code == 404
    assert calls == []


@pytest.fixture
def blocked(monkeypatch):
    """関門への待機記録を記録用モックに差し替える。"""
    calls = []
    monkeypatch.setattr(
        app_mod.RateLimitGate, "block", lambda self, name, resets_at: calls.append((name, resets_at))
    )
    return calls


def test_receive_rate_limit(client, blocked, session_factory, monkeypatch):
    """会話ログから読んだ時刻での待機開始を確認する（正常系）。"""
    # 準備
    monkeypatch.setattr(app_mod, "resolve_reset_at", lambda path, now: RESETS_AT)
    session = session_factory("architect", 170)
    # 実行
    response = client.post(
        "/rate_limit",
        json={
            "project": "sandbox",
            "agent_name": "architect",
            "number": 170,
            "transcript_path": "/home/user/.claude/projects/-mnt-c-repo/5a00ce9c.jsonl",
        },
    )
    # 検証: 読んだ時刻で待機が開始され resets_at が返る
    assert response.status_code == 200
    assert response.json() == {"resets_at": RESETS_AT.isoformat()}
    assert blocked == [(session.session_name, RESETS_AT)]


def test_receive_rate_limit_when_unparsable(client, blocked, mon_settings, session_factory, monkeypatch):
    """時刻を読めない場合の既定の待機時間を確認する（正常系）。"""
    # 準備
    monkeypatch.setattr(app_mod, "resolve_reset_at", lambda path, now: None)
    session_factory("architect", 170)
    before = datetime.now(timezone.utc)
    # 実行
    response = client.post(
        "/rate_limit",
        json={
            "project": "sandbox",
            "agent_name": "architect",
            "number": 170,
            "transcript_path": "/home/user/.claude/projects/-mnt-c-repo/5a00ce9c.jsonl",
        },
    )
    # 検証: 現在時刻 + rate_limit_fallback_min で待機が開始される
    assert response.status_code == 200
    _, resets_at = blocked[0]
    fallback = timedelta(minutes=mon_settings.rate_limit_fallback_min)
    assert before + fallback <= resets_at <= datetime.now(timezone.utc) + fallback


def test_receive_rate_limit_when_session_missing(client, blocked, monkeypatch):
    """台帳に無いセッションからの通知を拒否する（異常系）。"""
    # 準備
    calls = []
    monkeypatch.setattr(app_mod, "resolve_reset_at", lambda path, now: calls.append(path))
    # 実行
    response = client.post(
        "/rate_limit",
        json={
            "project": "sandbox",
            "agent_name": "architect",
            "number": 999,
            "transcript_path": "/home/user/.claude/projects/-mnt-c-repo/5a00ce9c.jsonl",
        },
    )
    # 検証: 404 が返り待機が開始されない
    assert response.status_code == 404
    assert blocked == []
    assert calls == []


# ---- ポーリングループ ----


def test_create_app_when_heartbeat(mon_settings, mon_registry, agents, monkeypatch, label_settings, tmp_path):
    """ループが 1 周ごとに最終周回時刻を書くことを確認する（正常系）。"""
    # 準備
    import ai_monitor.main as main_mod

    monkeypatch.setattr(main_mod, "run_cycle", lambda *a, **k: ({}, "1970-01-01T00:00:00+00:00"))
    beat_path = tmp_path / "monitor.heartbeat"
    supervised: list[object] = []
    app = app_mod.create_app(
        mon_settings, registry=mon_registry, agents=agents, label_settings=label_settings,
        heartbeat_path=beat_path, supervise_watchdog=lambda now: supervised.append(now),
    )
    # 実行
    with TestClient(app, base_url="http://localhost:8765"):
        for _ in range(50):
            if beat_path.exists() and supervised:
                break
            time.sleep(0.05)
    # 検証
    assert beat_path.exists(), "最終周回時刻が書かれていない"
    assert supervised, "監視役の監視が呼ばれていない"


def test_create_app_when_cycle_raised(mon_settings, mon_registry, agents, monkeypatch, label_settings):
    """ポーリングループの異常終了でプロセス終了が呼ばれることを確認する（正常系）。"""
    # 準備
    import ai_monitor.main as main_mod

    def _raise(*args, **kwargs):
        raise RuntimeError("周期の失敗")

    monkeypatch.setattr(main_mod, "run_cycle", _raise)
    exited: list[bool] = []
    app = app_mod.create_app(
        mon_settings, registry=mon_registry, agents=agents, label_settings=label_settings,
        exit_process=lambda: exited.append(True),
    )
    # 実行
    with TestClient(app, base_url="http://localhost:8765"):
        for _ in range(50):
            if exited:
                break
            time.sleep(0.05)
    # 検証
    assert exited, "ループが無言で消えている"
