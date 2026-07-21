"""`src/ai_monitor/server/app.py` の単体テスト。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import ai_monitor.server.app as app_mod
import ai_monitor.features.sessions.registry as registry_mod
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.sessions.types import AgentSession


@pytest.fixture
def agents() -> list[Agent]:
    return [Agent(name="architect", confirm_label="確認:architect", processing_label="処理中:architect", model="sonnet")]


@pytest.fixture
def registry(tmp_state_path, monkeypatch):
    monkeypatch.setattr(registry_mod, "save_sessions", MagicMock())
    reg = registry_mod.SessionRegistry(tmp_state_path)
    reg.register(
        AgentSession(
            session_name="ai-monitor-sandbox-52-architect",
            project="sandbox",
            agent_name="architect",
            primary_number=52,
            watch_numbers=[60],
        )
    )
    return reg


@pytest.fixture
def remove_label_mock(monkeypatch):
    mock = MagicMock(name="remove_label")
    monkeypatch.setattr(app_mod, "remove_label", mock)
    return mock


@pytest.fixture
def client(registry, agents, remove_label_mock, mon_project):
    settings = MagicMock()
    settings.projects = [mon_project]
    app = app_mod.create_app(settings, registry=registry, agents=agents)
    return TestClient(app)


def test_create_app(client):
    """ルーティング登録を確認する（正常系）。"""
    # 実行
    completion = client.post(
        "/completions", json={"project": "sandbox", "agent_name": "architect", "number": 52}
    )
    add = client.post(
        "/watch-targets",
        json={"project": "sandbox", "agent_name": "architect", "number": 52, "watch_numbers": [61]},
    )
    remove = client.request(
        "DELETE",
        "/watch-targets",
        json={"project": "sandbox", "agent_name": "architect", "number": 52, "watch_numbers": [61]},
    )
    # 検証
    assert completion.status_code == 200 and completion.json() == {"ok": True}
    assert add.status_code == 200
    assert remove.status_code == 200


def test_create_app_when_unknown_path(client):
    """未知パスの 404 を確認する（正常系）。"""
    # 実行
    response = client.get("/unknown")
    # 検証
    assert response.status_code == 404


def test_handle_completion(registry, agents, remove_label_mock, mon_project):
    """ラベル除去 + 生存更新を確認する（正常系）。"""
    # 準備
    before = registry.find("sandbox", "architect", 52).last_seen_at
    payload = app_mod.CompletionPayload(project="sandbox", agent_name="architect", number=52)
    # 実行
    result = app_mod.handle_completion(payload, registry=registry, agents=agents, projects=[mon_project])
    # 検証
    assert result == {"ok": True}
    assert remove_label_mock.call_args.args[2] == "処理中:architect"
    assert registry.find("sandbox", "architect", 52).last_seen_at != before


def test_handle_completion_when_session_missing(registry, agents, remove_label_mock, mon_project):
    """セッション不明を確認する（異常系）。"""
    # 準備
    payload = app_mod.CompletionPayload(project="sandbox", agent_name="architect", number=99)
    # 実行・検証
    with pytest.raises(HTTPException):
        app_mod.handle_completion(payload, registry=registry, agents=agents, projects=[mon_project])
    remove_label_mock.assert_not_called()


def test_handle_add_watch(registry):
    """監視面の追加を確認する（正常系）。"""
    # 準備
    payload = app_mod.WatchPayload(project="sandbox", agent_name="architect", number=52, watch_numbers=[61])
    # 実行
    result = app_mod.handle_add_watch(payload, registry=registry)
    # 検証
    assert result == {"ok": True}
    assert registry.find("sandbox", "architect", 52).watch_numbers == [60, 61]


def test_handle_add_watch_when_session_missing(registry):
    """セッション不明を確認する（異常系）。"""
    # 準備
    payload = app_mod.WatchPayload(project="sandbox", agent_name="architect", number=99, watch_numbers=[61])
    # 実行・検証
    with pytest.raises(HTTPException):
        app_mod.handle_add_watch(payload, registry=registry)


def test_handle_remove_watch(registry):
    """監視面の除去を確認する（正常系）。"""
    # 準備
    payload = app_mod.WatchPayload(project="sandbox", agent_name="architect", number=52, watch_numbers=[60])
    # 実行
    result = app_mod.handle_remove_watch(payload, registry=registry)
    # 検証
    assert result == {"ok": True}
    assert registry.find("sandbox", "architect", 52).watch_numbers == []


def test_handle_remove_watch_when_session_missing(registry):
    """セッション不明を確認する（異常系）。"""
    # 準備
    payload = app_mod.WatchPayload(project="sandbox", agent_name="architect", number=99, watch_numbers=[60])
    # 実行・検証
    with pytest.raises(HTTPException):
        app_mod.handle_remove_watch(payload, registry=registry)
