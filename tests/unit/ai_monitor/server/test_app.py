"""`src/ai_monitor/server/app.py` の単体テスト。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import ai_monitor.server.app as app_mod
from ai_monitor.features.agents.types import Agent


@pytest.fixture
def agents() -> list[Agent]:
    return [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet")]


@pytest.fixture
def client(mon_settings, mon_registry, agents, monkeypatch):
    import ai_monitor.main as main_mod

    # lifespan が起動するポーリングループを空回しにする
    monkeypatch.setattr(main_mod, "run_cycle", lambda *args, **kwargs: ({}, "1970-01-01T00:00:00+00:00"))
    app = app_mod.create_app(mon_settings, registry=mon_registry, agents=agents)
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


def test_receive_compaction(client, mon_settings, session_factory, monkeypatch):
    """コンパクト通知の受理と再送を確認する（正常系）。"""
    # 準備
    sent = []
    monkeypatch.setattr(app_mod, "send_keys", lambda name, text: sent.append((name, text)))
    monkeypatch.setattr(app_mod, "build_agent_docs", lambda *a, **kw: "## フェーズ\n\n# 初期処理\n")
    session = session_factory("architect", 170)
    # 実行
    response = client.post(
        "/compaction",
        json={"project": "sandbox", "agent_name": "architect", "number": 170},
    )
    # 検証: 該当セッションへ 1 回送信され受理される
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(sent) == 1
    assert sent[0][0] == session.session_name
    assert "# 初期処理" in sent[0][1]


def test_receive_compaction_when_session_missing(client, monkeypatch):
    """台帳に無いセッションからの通知を拒否する（異常系）。"""
    # 準備
    sent = []
    monkeypatch.setattr(app_mod, "send_keys", lambda name, text: sent.append((name, text)))
    # 実行
    response = client.post(
        "/compaction",
        json={"project": "sandbox", "agent_name": "architect", "number": 999},
    )
    # 検証
    assert response.status_code == 404
    assert sent == []
