"""「コンテキストリセット」の結合テスト。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import ai_monitor.server.app as app_mod
from ai_monitor.features.agents import docs
from ai_monitor.main import build_agents

HARNESS_README = (
    "## 目次\n\n"
    "| ページ | 概要 |\n"
    "| --- | --- |\n"
    "| [対応表](./共通対応表/対応表.md) | 共通の星取り表 |\n"
)
COMMON_MATRIX = (
    "| ドキュメント | subsystem-conductor |\n"
    "| --- | --- |\n"
    "| [規約/コメント.md](../../規約/コメント.md) | ○ |\n"
)
WIKI_README = (
    "## 目次\n\n"
    "| ページ | 概要 |\n"
    "| --- | --- |\n"
    "| [規約](./規約.md) | 規約ページ |\n"
)


def _write(root, pages):
    """一時ディレクトリにページ群を作成し、ベースとなる絶対パスを返す。"""
    for rel, body in pages.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return str(root)


@pytest.fixture
def wiki(tmp_path, monkeypatch, mon_settings, mon_project):
    """フェーズ設定と両 Wiki をローカルに用意する。"""
    common = _write(
        tmp_path / "ai-monitor-wiki",
        {
            "Claudeハーネス/README.md": HARNESS_README,
            "Claudeハーネス/共通対応表/対応表.md": COMMON_MATRIX,
            "規約/コメント.md": "# 規約: コメント\n",
            "エージェント/sc/フェーズ/初期処理.md": "# 初期処理\n",
        },
    )
    project = _write(tmp_path / "project-wiki", {"README.md": WIKI_README, "規約.md": "# 規約\n"})
    phases = tmp_path / "agent_phases.yaml"
    phases.write_text(
        "subsystem-conductor:\n  - エージェント/sc/フェーズ/初期処理.md\n", encoding="utf-8"
    )
    monkeypatch.setattr(docs, "PHASE_CONFIG_PATH", phases)
    mon_settings.ai_monitor_wiki_base = common
    mon_project.wiki_base = project


@pytest.fixture
def client(mon_settings, mon_registry, label_settings, agent_models, monkeypatch, wiki):
    """リセット要求を受けるアプリのテストクライアントを返す。"""
    import ai_monitor.main as main_mod

    # lifespan が起動するポーリングループを空回しにする
    monkeypatch.setattr(
        main_mod, "run_cycle", lambda *args, **kwargs: ({}, "1970-01-01T00:00:00+00:00")
    )
    agents = build_agents(label_settings, agent_models=agent_models)
    app = app_mod.create_app(mon_settings, registry=mon_registry, agents=agents)
    with TestClient(app, base_url="http://localhost:8765") as client:
        yield client


def test_normal(client, tmux_calls, session_factory):
    """要求の受理 → 該当セッションへの /clear + ドキュメント送信を確認する（正常系）。"""
    # 準備
    session = session_factory("subsystem-conductor", 170)
    # 実行
    response = client.post(
        "/context_reset",
        json={"project": "sandbox", "agent_name": "subsystem-conductor", "number": 170},
    )
    # 検証: 200 + 該当セッションへ /clear → ドキュメントの順で送信
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    # send_keys は本文と Enter で 2 回 tmux を呼ぶため、本文送信だけを数える
    sends = [c for c in tmux_calls.calls if c[0] == "send-keys" and c[3] != "Enter"]
    assert len(sends) == 2
    assert all(c[2] == session.session_name for c in sends)
    assert sends[0][3] == "/clear"
    # フェーズ + 参考資料 + Wiki 索引が載る
    sent_text = sends[1][3]
    assert "# 初期処理" in sent_text
    assert "# 規約: コメント" in sent_text
    assert "規約.md" in sent_text


def test_error_when_session_missing(client, tmux_calls):
    """台帳に無いセッションからの要求を拒否することを確認する（異常系）。"""
    # 実行
    response = client.post(
        "/context_reset",
        json={"project": "sandbox", "agent_name": "subsystem-conductor", "number": 999},
    )
    # 検証: 404 + tmux への送信なし
    assert response.status_code == 404
    assert [c for c in tmux_calls.calls if c[0] == "send-keys"] == []
