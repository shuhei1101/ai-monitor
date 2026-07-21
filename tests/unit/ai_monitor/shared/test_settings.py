"""`src/ai_monitor/shared/settings.py` の単体テスト。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

import ai_monitor.shared.settings as settings_mod

_ALL_AGENT_NAMES = [
    "intake-issue-triager", "epic-conductor", "epic-poc-runner", "mock-designer",
    "complex-scenario-writer", "complex-scenario-tester", "story-conductor",
    "single-scenario-writer", "single-scenario-tester", "subsystem-conductor",
    "architect", "library-poc-runner", "tester", "implementer", "resetter",
    "quick-implementer", "questioner",
]


def _agents_yaml(names=_ALL_AGENT_NAMES) -> str:
    """全 17 エージェント分の agents セクション文字列を生成する。"""
    return "agents:\n" + "".join(f"  {name}:\n    model: sonnet\n" for name in names)


BASE_YAML = """github_token: github_pat_test
port: 18999
poll_interval_sec: 5
session_timeout_min: 10
heartbeat_interval_sec: 20
state_path: data/state.yaml
projects:
  - name: sandbox
    repo: shuhei1101/ai-monitor-e2e
    local_path: /tmp/sandbox
    wiki_base: https://example.com/wiki
""" + _agents_yaml()


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch):
    """一時フォルダを設定ディレクトリとして読み込ませる。"""
    monkeypatch.setattr(settings_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.delenv("AI_MONITOR_ENV", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    (tmp_path / "settings.yaml").write_text(BASE_YAML, encoding="utf-8")
    return tmp_path


def test_settings(tmp_config_dir):
    """yaml からの読み込みを確認する（正常系）。"""
    # 実行
    settings = settings_mod.Settings()
    # 検証
    assert settings.github_token.get_secret_value() == "github_pat_test"
    assert settings.port == 18999
    assert settings.poll_interval_sec == 5
    assert settings.session_timeout_min == 10
    assert settings.heartbeat_interval_sec == 20
    assert settings.state_path == "data/state.yaml"
    assert settings.projects[0].name == "sandbox"
    assert settings.projects[0].repo == "shuhei1101/ai-monitor-e2e"


def test_settings_when_env_var_set(tmp_config_dir, monkeypatch):
    """同名環境変数の上書きを確認する（正常系）。"""
    # 準備
    monkeypatch.setenv("PORT", "19999")
    # 実行
    settings = settings_mod.Settings()
    # 検証
    assert settings.port == 19999


def test_settings_when_env_file_given(tmp_config_dir, monkeypatch):
    """環境差分ファイルの上書きを確認する（正常系）。"""
    # 準備
    monkeypatch.setenv("AI_MONITOR_ENV", "e2e")
    (tmp_config_dir / "settings.e2e.yaml").write_text("port: 28999\n", encoding="utf-8")
    # 実行
    settings = settings_mod.Settings()
    # 検証
    assert settings.port == 28999
    assert settings.github_token.get_secret_value() == "github_pat_test"


def test_settings_when_token_missing(tmp_config_dir):
    """`github_token` 未設定のバリデーションエラーを確認する（異常系）。"""
    # 準備
    yaml_without_token = "\n".join(
        line for line in BASE_YAML.splitlines() if not line.startswith("github_token")
    )
    (tmp_config_dir / "settings.yaml").write_text(yaml_without_token, encoding="utf-8")
    # 実行・検証
    with pytest.raises(ValidationError):
        settings_mod.Settings()


def test_settings_when_agents_all_set(tmp_config_dir):
    """全エージェント分のモデル読み込みを確認する（正常系）。"""
    # 実行
    settings = settings_mod.Settings()
    # 検証
    assert set(settings.agents.keys()) == set(_ALL_AGENT_NAMES)
    assert all(agent.model == "sonnet" for agent in settings.agents.values())


def test_settings_when_agents_missing_entry(tmp_config_dir):
    """エージェントエントリ欠落のバリデーションエラーを確認する（異常系）。"""
    # 準備: implementer だけ書かない settings.yaml
    without_impl = [n for n in _ALL_AGENT_NAMES if n != "implementer"]
    yaml_partial = BASE_YAML.split("agents:", 1)[0] + _agents_yaml(without_impl)
    (tmp_config_dir / "settings.yaml").write_text(yaml_partial, encoding="utf-8")
    # 実行・検証
    with pytest.raises(ValidationError) as exc_info:
        settings_mod.Settings()
    assert "implementer" in str(exc_info.value)


def test_settings_when_agents_empty_model(tmp_config_dir):
    """モデル空文字のバリデーションエラーを確認する（異常系）。"""
    # 準備: implementer の model を空文字にする
    yaml_empty = BASE_YAML.replace(
        "  implementer:\n    model: sonnet\n",
        "  implementer:\n    model: ''\n",
    )
    (tmp_config_dir / "settings.yaml").write_text(yaml_empty, encoding="utf-8")
    # 実行・検証
    with pytest.raises(ValidationError):
        settings_mod.Settings()


def test_agent_model_when_empty():
    """AgentModel の空文字禁止を確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(ValidationError):
        settings_mod.AgentModel(model="")
