"""composition root（設定読込・配線・起動）。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from ai_monitor.features.agents.service import poll
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.cleanup.service import (
    close_completed_intakes,
    reap_timed_out_sessions,
    release_closed_epics,
    release_closed_standalone,
)
from ai_monitor.features.sessions.registry import SessionRegistry
from ai_monitor.integrations.github.client import get_client
from ai_monitor.integrations.github.search import list_open_targets
from ai_monitor.server.app import create_app
from ai_monitor.shared.settings import _AGENT_NAMES, AgentModel, LabelSettings, Settings
from ai_monitor.shared.types import MonitorTarget

logger = logging.getLogger(__name__)

_STANDALONE_NAMES = {"epic-poc-runner", "library-poc-runner", "resetter", "quick-implementer", "questioner"}


def build_agents(labels: LabelSettings, *, agent_models: dict[str, AgentModel]) -> list[Agent]:
    """全エージェントの Agent をラベル設定と agent_models の値から組み立てる。"""
    agents = []
    for name in _AGENT_NAMES:
        field = name.replace("-", "_")
        # 確認 / 処理中ラベル + モデルを取り出して組み立てる（独立系 5 種は standalone=True）
        agents.append(
            Agent(
                name=name,
                confirm_label=getattr(labels, f"confirm_{field}"),
                processing_label=getattr(labels, f"processing_{field}"),
                model=agent_models[name].model,
                standalone=name in _STANDALONE_NAMES,
            )
        )
    return agents


def run_cycle(
    settings: Settings,
    agents: list[Agent],
    *,
    registry: SessionRegistry,
    prev_targets: dict[str, list[MonitorTarget]],
    last_heartbeat_at: str,
) -> tuple[dict[str, list[MonitorTarget]], str]:
    """ポーリング + クリーンアップ検知 + heartbeat 判定の 1 周期を実行する。"""
    standalone_names = {agent.name for agent in agents if agent.standalone}
    now = datetime.now(timezone.utc)
    # 前回 heartbeat からの経過を判定する
    elapsed_sec = (now - datetime.fromisoformat(last_heartbeat_at)).total_seconds()
    heartbeat_elapsed = elapsed_sec >= settings.heartbeat_interval_sec
    targets_by_project: dict[str, list[MonitorTarget]] = {}
    for project in settings.projects:
        # 手順内で例外が発生したプロジェクトは周期を見送る（ログのみ・次周期で再試行）
        try:
            # open 対象一覧を取得する（周期 1 回・全エージェントで共有）
            targets = list_open_targets(project)
            targets_by_project[project.name] = targets
            # プロジェクト × エージェントの対ごとにポーリングを実行する
            for agent in agents:
                poll(project, agent, targets, registry=registry)
            # クリーンアップ検知を実行する
            close_completed_intakes(project, targets)
            release_closed_epics(project, targets, prev_targets.get(project.name, []), registry=registry)
            release_closed_standalone(project, targets, registry=registry, standalone_names=standalone_names)
            # heartbeat 間隔が経過していればタイムアウト回収を実行する
            if heartbeat_elapsed:
                reap_timed_out_sessions(
                    project, targets, registry=registry, agents=agents, timeout_min=settings.session_timeout_min
                )
        except Exception:
            logger.exception("周期を見送ります: project=%s", project.name)
            targets_by_project.pop(project.name, None)
    if heartbeat_elapsed:
        last_heartbeat_at = now.isoformat()
    return targets_by_project, last_heartbeat_at


def main() -> int:
    """設定読込 → 台帳復元 → FastAPI アプリ起動を行う。"""
    settings = Settings()
    labels = LabelSettings()
    get_client(settings)
    agents = build_agents(labels, agent_models=settings.agents)
    registry = SessionRegistry(Path(settings.state_path))
    app = create_app(settings, registry=registry, agents=agents)
    uvicorn.run(app, host="127.0.0.1", port=settings.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
