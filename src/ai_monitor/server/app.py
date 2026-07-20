"""モニターの FastAPI アプリ（HTTP 受信 + ポーリングループの駆動）。"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ai_monitor.features.agents.types import Agent
from ai_monitor.integrations.github.labels import remove_label
from ai_monitor.shared.settings import MonitoredProject, Settings

if TYPE_CHECKING:
    from ai_monitor.features.sessions.registry import SessionRegistry


class CompletionPayload(BaseModel):
    """`POST /completions` の受信ボディ。"""

    project: str
    agent_name: str
    number: int


class WatchPayload(BaseModel):
    """`POST /watch-targets` / `DELETE /watch-targets` の受信ボディ。"""

    project: str
    agent_name: str
    number: int
    watch_numbers: list[int]


def create_app(settings: Settings, *, registry: SessionRegistry, agents: list[Agent]) -> FastAPI:
    """FastAPI アプリを生成してルーティングと lifespan を配線する。"""

    # lifespan でポーリングループをバックグラウンドスレッドとして起動する
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from ai_monitor.main import run_cycle

        stop = threading.Event()

        def loop() -> None:
            prev_targets: dict = {}
            heartbeat_at = "1970-01-01T00:00:00+00:00"
            while not stop.is_set():
                prev_targets, heartbeat_at = run_cycle(
                    settings,
                    agents,
                    registry=registry,
                    prev_targets=prev_targets,
                    last_heartbeat_at=heartbeat_at,
                )
                stop.wait(settings.poll_interval_sec)

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        yield
        stop.set()

    app = FastAPI(lifespan=lifespan)

    @app.post("/completions")
    def completions(payload: CompletionPayload) -> dict:
        return handle_completion(payload, registry=registry, agents=agents, projects=settings.projects)

    @app.post("/watch-targets")
    def add_watch(payload: WatchPayload) -> dict:
        return handle_add_watch(payload, registry=registry)

    @app.delete("/watch-targets")
    def remove_watch(payload: WatchPayload) -> dict:
        return handle_remove_watch(payload, registry=registry)

    return app


def handle_completion(
    payload: CompletionPayload,
    *,
    registry: SessionRegistry,
    agents: list[Agent],
    projects: list[MonitoredProject],
) -> dict:
    """作業完了報告を受けて `処理中:*` ラベルを外し、生存時刻を更新する。"""
    # セッションと監視対象プロジェクトを解決する（いずれも無ければ 404）
    session = registry.find(payload.project, payload.agent_name, payload.number)
    project = next((p for p in projects if p.name == payload.project), None)
    if session is None or project is None:
        raise HTTPException(status_code=404, detail="session not found")
    # 処理中ラベルを除去する（未付与は無視される冪等操作）
    processing_label = next((a.processing_label for a in agents if a.name == payload.agent_name), None)
    if processing_label is not None:
        remove_label(project, payload.number, processing_label)
    # 生存時刻を更新する
    registry.touch(session.session_name)
    return {"ok": True}


def handle_add_watch(payload: WatchPayload, *, registry: SessionRegistry) -> dict:
    """派生 PR の番号をセッションの監視面へ追加する。"""
    try:
        registry.add_watch(payload.project, payload.agent_name, payload.number, payload.watch_numbers)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    return {"ok": True}


def handle_remove_watch(payload: WatchPayload, *, registry: SessionRegistry) -> dict:
    """セッションの監視面から番号を取り除く。"""
    try:
        registry.remove_watch(payload.project, payload.agent_name, payload.number, payload.watch_numbers)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    return {"ok": True}
