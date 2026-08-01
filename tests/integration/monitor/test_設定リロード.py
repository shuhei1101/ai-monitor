"""「設定リロード」の結合テスト。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import ai_monitor.server.app as app_mod
from ai_monitor.main import build_agents


def _settings(*project_names: str, port: int = 8765, state_path: str = "data/state.yaml"):
    """監視対象と実行中に変えられない項目を指定して実物の Settings を作る。"""
    from ai_monitor.shared.settings import _AGENT_NAMES, AgentSettings, MonitoredProject, Settings

    return Settings(
        github_token="github_pat_test",
        ai_monitor_wiki_base="https://example.com/ai-monitor-wiki",
        port=port,
        state_path=state_path,
        agents={name: AgentSettings(model="sonnet") for name in _AGENT_NAMES},
        projects=[
            MonitoredProject(
                name=name,
                repo=f"shuhei1101/{name}",
                local_path=f"/tmp/{name}",
                wiki_base="https://example.com/wiki",
            )
            for name in project_names
        ],
    )


@pytest.fixture
def client_factory(gh_mon, mon_registry, label_settings, notify, monkeypatch):
    """設定と読込関数を指定してアプリを起動する factory（ポーリングは空回し）。"""
    import ai_monitor.main as main_mod

    monkeypatch.setattr(main_mod, "run_cycle", lambda *args, **kwargs: ({}, "1970-01-01T00:00:00+00:00"))

    def _make(settings, read_settings):
        agents = build_agents(label_settings, agent_settings=settings.agents)
        app = app_mod.create_app(
            settings,
            registry=mon_registry,
            agents=agents,
            label_settings=label_settings,
            notify=notify,
            read_settings=read_settings,
            build_agents=lambda s: build_agents(label_settings, agent_settings=s.agents),
        )
        return TestClient(app, base_url="http://localhost:8765"), settings, agents

    return _make


def test_normal(client_factory):
    """設定の読み直しと差し替え、増減の返却を確認する（正常系）。"""
    # 準備
    settings = _settings("sandbox")
    latest = _settings("sandbox", "extra")
    client, settings, agents = client_factory(settings, lambda: latest)
    # 実行
    with client:
        response = client.post("/reload")
    # 検証
    assert response.status_code == 200
    body = response.json()
    assert body["added"] == ["extra"]
    assert body["removed"] == []
    assert body["ignored"] == []
    # ポーリングと MCP が見ている実体が差し替わっている
    assert [p.name for p in settings.projects] == ["sandbox", "extra"]


def test_normal_when_fixed_changed(client_factory):
    """実行中に変えられない項目の据え置きを確認する（正常系）。"""
    # 準備
    settings = _settings("sandbox")
    latest = _settings("sandbox", port=9999, state_path="data/other.yaml")
    client, settings, _agents = client_factory(settings, lambda: latest)
    # 実行
    with client:
        response = client.post("/reload")
    # 検証
    assert response.status_code == 200
    ignored = {item["item"]: item["reason"] for item in response.json()["ignored"]}
    assert set(ignored) == {"port", "state_path"}
    assert all("再起動" in reason for reason in ignored.values())
    assert settings.port == 8765
    assert settings.state_path == "data/state.yaml"


def test_error_when_unreadable(client_factory):
    """読込失敗時に直前の設定を保つことを確認する（異常系）。"""
    # 準備
    settings = _settings("sandbox")

    def _raise():
        raise ValueError("設定ファイルの構文が不正です")

    client, settings, agents = client_factory(settings, _raise)
    models_before = [a.model for a in agents]
    # 実行
    with client:
        response = client.post("/reload")
    # 検証
    assert response.status_code == 500
    assert "構文" in response.json()["detail"]
    assert [p.name for p in settings.projects] == ["sandbox"]
    assert [a.model for a in agents] == models_before
