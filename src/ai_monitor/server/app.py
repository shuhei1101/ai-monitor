"""モニターの FastAPI アプリ（MCP のマウント + ポーリングループの駆動）。"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ai_monitor.features.agents.service import reset_session
from ai_monitor.features.agents.types import Agent
from ai_monitor.mcp.server import build_mcp_app
from ai_monitor.shared.settings import Settings

if TYPE_CHECKING:
    from ai_monitor.features.sessions.registry import SessionRegistry

logger = logging.getLogger(__name__)


class ContextResetRequest(BaseModel):
    """`POST /context_reset` のリクエストボディ。"""

    project: str
    agent_name: str
    number: int


def create_app(settings: Settings, *, registry: SessionRegistry, agents: list[Agent]) -> FastAPI:
    """FastAPI アプリを生成し、MCP のマウントと lifespan を配線する。"""
    # MCP サーバーの ASGI アプリを組み立てる
    mcp_app = build_mcp_app(settings, registry=registry, agents=agents)

    # lifespan で MCP のセッション管理を開始し、その内側でポーリングループを起動する
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

        async with mcp_app.router.lifespan_context(mcp_app):
            thread = threading.Thread(target=loop, daemon=True)
            thread.start()
            yield
            stop.set()

    # FastAPI アプリを生成する
    app = FastAPI(lifespan=lifespan)

    @app.post("/context_reset")
    def receive_context_reset(body: ContextResetRequest) -> dict:
        """リセット要求を受け、該当セッションを作り直して起動プロンプトを送り直す。"""
        # 台帳からセッションを検索する
        session = registry.find(body.project, body.agent_name, body.number)
        if session is None:
            logger.warning(
                "台帳に無いセッションからのリセット要求を拒否しました: "
                "project=%s agent_name=%s number=%s",
                body.project,
                body.agent_name,
                body.number,
            )
            raise HTTPException(status_code=404)
        # 設定から対象プロジェクトとエージェント定義を引く
        project = next(p for p in settings.projects if p.name == body.project)
        agent = next(a for a in agents if a.name == body.agent_name)
        # セッションを作り直して起動プロンプトを送り直す
        reset_session(
            session,
            project,
            agent,
            telemetry=settings.telemetry,
            port=settings.port,
            ai_monitor_wiki_base=settings.ai_monitor_wiki_base,
        )
        return {"ok": True}

    # MCP の ASGI アプリをルートにマウントする（接続先は /mcp）
    # マウントは後続の全パスを引き受けるため、自前のルート登録より後に行う
    app.mount("/", mcp_app)
    return app
