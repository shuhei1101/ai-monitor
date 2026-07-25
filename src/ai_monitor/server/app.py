"""モニターの FastAPI アプリ（MCP のマウント + ポーリングループの駆動）。"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from ai_monitor.features.agents.types import Agent
from ai_monitor.mcp.server import build_mcp_app
from ai_monitor.shared.settings import Settings

if TYPE_CHECKING:
    from ai_monitor.features.sessions.registry import SessionRegistry

logger = logging.getLogger(__name__)


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

    # FastAPI アプリを生成し、MCP の ASGI アプリをルートにマウントする（接続先は /mcp）
    app = FastAPI(lifespan=lifespan)
    app.mount("/", mcp_app)
    return app
