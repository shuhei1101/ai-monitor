"""設定の読み込み（settings.yaml / constants.env）。"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from ai_monitor.shared.types import LabelName

CONFIG_DIR = Path.home() / ".config" / "ai-monitor"
CONSTANTS_ENV = Path(__file__).resolve().parents[3] / "plugins" / "ai-monitor" / "constants.env"

_AGENT_NAMES: tuple[str, ...] = (
    "intake-issue-triager",
    "epic-conductor",
    "epic-poc-runner",
    "mock-designer",
    "complex-scenario-writer",
    "complex-scenario-tester",
    "story-conductor",
    "single-scenario-writer",
    "single-scenario-tester",
    "subsystem-conductor",
    "architect",
    "library-poc-runner",
    "tester",
    "implementer",
    "resetter",
    "quick-implementer",
    "questioner",
)


class AgentModel(BaseModel):
    """エージェント別のモデル設定 1 件分。"""

    model: str = Field(min_length=1)


class MonitoredProject(BaseModel):
    """監視対象プロジェクト 1 件分の設定。"""

    name: str
    repo: str
    local_path: str
    wiki_base: str


class Settings(BaseSettings):
    """`~/.config/ai-monitor/settings.yaml` を型安全に読む全体設定。"""

    model_config = SettingsConfigDict(extra="ignore")

    github_token: SecretStr
    port: int = 8765
    poll_interval_sec: int = 15
    session_timeout_min: int = 30
    heartbeat_interval_sec: int = 60
    state_path: str = "data/state.yaml"
    projects: list[MonitoredProject] = []
    agents: dict[str, AgentModel]

    @model_validator(mode="after")
    def _validate_agents_completeness(self):
        """agents に全 17 エージェント分のエントリが揃っていることを検証する。"""
        # 欠落しているエージェント名を列挙して起動を止める（フォールバックしない）
        missing = [name for name in _AGENT_NAMES if name not in self.agents]
        if missing:
            raise ValueError(f"settings.agents に欠落しているエージェント: {missing}")
        return self

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        # 優先度: 明示引数 > 環境変数 > 環境差分 yaml > 共通 yaml
        sources = [init_settings, env_settings]
        env_name = os.environ.get("AI_MONITOR_ENV")
        if env_name:
            sources.append(
                YamlConfigSettingsSource(settings_cls, yaml_file=CONFIG_DIR / f"settings.{env_name}.yaml")
            )
        sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=CONFIG_DIR / "settings.yaml"))
        return tuple(sources)


class LabelSettings(BaseSettings):
    """`constants.env` の `AI_MONITOR_LABEL_*` を型安全に読むラベル設定。"""

    model_config = SettingsConfigDict(
        env_file=CONSTANTS_ENV, env_prefix="AI_MONITOR_LABEL_", extra="ignore"
    )

    in_discussion: LabelName
    confirm_intake_issue_triager: LabelName
    confirm_epic_conductor: LabelName
    confirm_epic_poc_runner: LabelName
    confirm_mock_designer: LabelName
    confirm_complex_scenario_writer: LabelName
    confirm_complex_scenario_tester: LabelName
    confirm_story_conductor: LabelName
    confirm_single_scenario_writer: LabelName
    confirm_single_scenario_tester: LabelName
    confirm_subsystem_conductor: LabelName
    confirm_architect: LabelName
    confirm_library_poc_runner: LabelName
    confirm_tester: LabelName
    confirm_implementer: LabelName
    confirm_resetter: LabelName
    confirm_quick_implementer: LabelName
    confirm_questioner: LabelName
    processing_intake_issue_triager: LabelName
    processing_epic_conductor: LabelName
    processing_epic_poc_runner: LabelName
    processing_mock_designer: LabelName
    processing_complex_scenario_writer: LabelName
    processing_complex_scenario_tester: LabelName
    processing_story_conductor: LabelName
    processing_single_scenario_writer: LabelName
    processing_single_scenario_tester: LabelName
    processing_subsystem_conductor: LabelName
    processing_architect: LabelName
    processing_library_poc_runner: LabelName
    processing_tester: LabelName
    processing_implementer: LabelName
    processing_resetter: LabelName
    processing_quick_implementer: LabelName
    processing_questioner: LabelName
