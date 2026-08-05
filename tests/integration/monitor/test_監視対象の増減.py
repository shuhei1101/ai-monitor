"""「監視対象の増減」の結合テスト。

エージェントも tmux も登場しないため、E2E ハーネスではなく実プロセス相当の組み立てで確認する。
設定ファイルを実際に書き換えて `POST /reload` を叩き、ポーリングと MCP の両方が
新しい設定を見るようになるまでを 1 本の流れで見る（エンドポイント単体は「設定リロード」の結合テスト）。
"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient

import ai_monitor.main as main_mod
import ai_monitor.mcp.server as mcp_server
import ai_monitor.server.app as app_mod
from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.main import build_agents, run_cycle
from ai_monitor.shared.settings import _AGENT_NAMES, Settings

FUTURE = "2100-01-01T00:00:00+00:00"


def _settings_doc(*project_names: str) -> dict:
    """settings.yaml に書き出す内容を組み立てる。"""
    return {
        "github_token": "github_pat_test",
        "ai_monitor_wiki_base": "https://example.com/ai-monitor-wiki",
        "agents": {name: {"model": "sonnet"} for name in _AGENT_NAMES},
        "projects": [
            {
                "name": name,
                "repo": f"shuhei1101/{name}",
                "local_path": f"/tmp/{name}",
                "wiki_base": "https://example.com/wiki",
            }
            for name in project_names
        ],
    }


def _resp(items):
    r = MagicMock()
    r.parsed_data = items
    return r


def _ctx(project: str):
    """X-Project ヘッダを持つ MCP リクエストコンテキストを作る。"""
    return NS(request_context=NS(request=NS(headers={"X-Project": project})))


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """一時ディレクトリの settings.yaml を読み込ませ、内容を書き換える factory を返す。"""
    import ai_monitor.shared.settings as settings_mod

    # 設定の読み先を一時ディレクトリへ向ける（起動時の読込も再読込も同じ場所を見る）
    monkeypatch.setattr(settings_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.delenv("AI_MONITOR_ENV", raising=False)
    path = tmp_path / "settings.yaml"

    def _write(*project_names: str) -> None:
        path.write_text(yaml.safe_dump(_settings_doc(*project_names), allow_unicode=True), encoding="utf-8")

    return _write


@pytest.fixture
def running_monitor(mon_registry, label_settings, notify, monkeypatch):
    """設定ファイルの内容で起動したアプリと、その設定・エージェント定義を返す factory。"""
    monkeypatch.setattr(main_mod, "run_cycle", lambda *args, **kwargs: ({}, FUTURE))

    def _start():
        settings = Settings()
        agents = build_agents(label_settings, agent_settings=settings.agents)
        app = app_mod.create_app(
            settings, registry=mon_registry, agents=agents, label_settings=label_settings, notify=notify
        )
        return app, settings, agents

    return _start


def _polled_repos(gh_mon, settings, agents, mon_registry, label_settings, notify, count: int) -> set[str]:
    """周期を 1 回回して、対象一覧を取得したリポジトリ名を返す。"""
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([]) for _ in range(count)]
    run_cycle(
        settings,
        agents,
        registry=mon_registry,
        prev_targets={},
        last_heartbeat_at=FUTURE,
        labels=label_settings,
        gate=RateLimitGate(),
        notified_gates={},
        notify=notify,
    )
    return {c.kwargs["repo"] for c in gh_mon.rest.issues.list_for_repo.call_args_list}


def test_normal(gh_mon, mon_registry, label_settings, notify, settings_file, running_monitor):
    """設定ファイルの編集 → 再読込 → ポーリングと MCP への反映を確認する（正常系）。"""
    # 準備: 監視対象 1 件で起動し、ファイル側を 2 件に書き換える
    settings_file("sandbox")
    app, settings, agents = running_monitor()
    settings_file("sandbox", "extra")
    # 実行
    with TestClient(app, base_url="http://localhost:8765") as client:
        response = client.post("/reload")
    # 検証: 応答に追加分が載っている
    assert response.status_code == 200
    assert response.json()["added"] == ["extra"]
    # 検証: 差し替え後の周期で追加分の対象一覧も取得される
    polled = _polled_repos(gh_mon, settings, agents, mon_registry, label_settings, notify, count=2)
    assert polled == {"sandbox", "extra"}
    # 検証: MCP が追加したプロジェクト名を解決できる
    assert mcp_server._resolve_project(_ctx("extra"), projects=settings.projects).repo == "shuhei1101/extra"


def test_normal_when_removed(
    gh_mon, mon_registry, label_settings, notify, settings_file, running_monitor
):
    """監視対象の削除の反映を確認する（正常系）。"""
    # 準備: 監視対象 2 件で起動し、ファイル側を 1 件に書き換える
    settings_file("sandbox", "extra")
    app, settings, agents = running_monitor()
    settings_file("sandbox")
    # 実行
    with TestClient(app, base_url="http://localhost:8765") as client:
        response = client.post("/reload")
    # 検証: 応答に削除分が載っている
    assert response.status_code == 200
    assert response.json()["removed"] == ["extra"]
    # 検証: 差し替え後の周期で削除分は取得されない
    polled = _polled_repos(gh_mon, settings, agents, mon_registry, label_settings, notify, count=1)
    assert polled == {"sandbox"}
    # 検証: MCP が削除したプロジェクト名を解決できない
    with pytest.raises(mcp_server.ProjectNotFoundError):
        mcp_server._resolve_project(_ctx("extra"), projects=settings.projects)
