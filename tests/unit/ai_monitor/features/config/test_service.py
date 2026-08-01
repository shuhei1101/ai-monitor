"""`src/ai_monitor/features/config/service.py` の単体テスト。"""
from __future__ import annotations

import pytest

from ai_monitor.features.agents.types import Agent
from ai_monitor.features.config.service import reload_settings
from ai_monitor.shared.settings import MonitoredProject


def _project(name: str) -> MonitoredProject:
    return MonitoredProject(
        name=name,
        repo=f"shuhei1101/{name}",
        local_path=f"/tmp/{name}",
        wiki_base="https://example.com/wiki",
    )


def _agent(model: str) -> Agent:
    return Agent(
        name="architect",
        confirm_label="確認:architect",
        processing_label="処理中:architect",
        model=model,
        effort="high",
    )


def _agents_setting() -> dict:
    from ai_monitor.shared.settings import _AGENT_NAMES, AgentSettings

    return {name: AgentSettings(model="sonnet") for name in _AGENT_NAMES}


@pytest.fixture
def settings_factory():
    """稼働中の設定を模した書き換え可能な Settings を作る factory。"""
    from ai_monitor.shared.settings import Settings

    def _make(**overrides):
        values = {
            "github_token": "github_pat_test",
            "ai_monitor_wiki_base": "https://example.com/ai-monitor-wiki",
            "agents": _agents_setting(),
            "projects": [_project("sandbox")],
            "port": 8765,
            "state_path": "data/state.yaml",
        }
        values.update(overrides)
        return Settings(**values)

    return _make


def test_reload_settings(settings_factory):
    """監視対象の追加を確認する（正常系）。"""
    # 準備
    current = settings_factory()
    latest = settings_factory(projects=[_project("sandbox"), _project("extra")])
    agents = [_agent("sonnet")]
    # 実行
    result = reload_settings(
        current, agents, read_settings=lambda: latest, build_agents=lambda s: [_agent("sonnet")]
    )
    # 検証
    assert result.added == ["extra"]
    assert result.removed == []
    assert [p.name for p in current.projects] == ["sandbox", "extra"]


def test_reload_settings_when_removed(settings_factory):
    """監視対象の削除を確認する（正常系）。"""
    # 準備
    current = settings_factory(projects=[_project("sandbox"), _project("extra")])
    latest = settings_factory(projects=[_project("sandbox")])
    agents = [_agent("sonnet")]
    # 実行
    result = reload_settings(
        current, agents, read_settings=lambda: latest, build_agents=lambda s: [_agent("sonnet")]
    )
    # 検証
    assert result.removed == ["extra"]
    assert result.added == []
    assert [p.name for p in current.projects] == ["sandbox"]


def test_reload_settings_when_unchanged(settings_factory):
    """増減なしのときの空応答を確認する（正常系）。"""
    # 準備
    current = settings_factory()
    latest = settings_factory()
    agents = [_agent("sonnet")]
    # 実行
    result = reload_settings(
        current, agents, read_settings=lambda: latest, build_agents=lambda s: [_agent("sonnet")]
    )
    # 検証
    assert result.added == []
    assert result.removed == []
    assert result.ignored == []


def test_reload_settings_when_fixed_changed(settings_factory):
    """実行中に変えられない項目の据え置きを確認する（正常系）。"""
    # 準備
    current = settings_factory()
    latest = settings_factory(port=9999, state_path="data/other.yaml")
    agents = [_agent("sonnet")]
    # 実行
    result = reload_settings(
        current, agents, read_settings=lambda: latest, build_agents=lambda s: [_agent("sonnet")]
    )
    # 検証
    assert {item.item for item in result.ignored} == {"port", "state_path"}
    assert all(item.reason for item in result.ignored)
    assert current.port == 8765
    assert current.state_path == "data/state.yaml"


def test_reload_settings_when_agents_rebuilt(settings_factory):
    """エージェント定義の作り直しを確認する（正常系）。"""
    # 準備
    current = settings_factory()
    latest = settings_factory()
    agents = [_agent("sonnet")]
    original = agents
    # 実行
    reload_settings(
        current, agents, read_settings=lambda: latest, build_agents=lambda s: [_agent("opus")]
    )
    # 検証: 配りっぱなしの参照へ効かせるためリストの同一性が保たれている
    assert agents is original
    assert [a.model for a in agents] == ["opus"]


def test_reload_settings_when_read_fails(settings_factory):
    """読込失敗時に稼働中の設定が変わらないことを確認する（異常系）。"""
    # 準備
    current = settings_factory()
    agents = [_agent("sonnet")]

    def _raise():
        raise ValueError("設定ファイルの構文が不正です")

    # 実行・検証
    with pytest.raises(ValueError, match="構文"):
        reload_settings(current, agents, read_settings=_raise, build_agents=lambda s: [])
    assert [p.name for p in current.projects] == ["sandbox"]
    assert [a.model for a in agents] == ["sonnet"]
