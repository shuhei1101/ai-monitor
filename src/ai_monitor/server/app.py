"""モニターの FastAPI アプリ（MCP のマウント + ポーリングループの駆動）。"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ai_monitor.features.agents.docs import build_agent_docs
from ai_monitor.features.agents.types import Agent
from ai_monitor.integrations.tmux.ops import send_escape, send_keys
from ai_monitor.mcp.server import build_mcp_app
from ai_monitor.shared.settings import Settings

if TYPE_CHECKING:
    from ai_monitor.features.sessions.registry import SessionRegistry

logger = logging.getLogger(__name__)

# 会話履歴を空にするスラッシュコマンド
CLEAR_COMMAND = "/clear"


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
        """リセット要求を受け、該当セッションを /clear してからドキュメントを送り直す。"""
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
        # 設定から対象プロジェクトを引き、エージェントドキュメントを組み立てる
        project = next(p for p in settings.projects if p.name == body.project)
        agent_docs = build_agent_docs(
            body.agent_name, project, ai_monitor_wiki_base=settings.ai_monitor_wiki_base
        )
        # コンパクト処理を中断してから /clear を打つ（処理中は入力が queue に積まれるだけで実行されない）
        send_escape(session.session_name)
        # /clear で空にしてからドキュメントを送り直す（順序を逆にすると消える）
        send_keys(session.session_name, CLEAR_COMMAND)
        send_keys(session.session_name, agent_docs)
        logger.info(
            "コンテキストをリセットしてドキュメントを送り直しました: project=%s agent_name=%s number=%s",
            body.project,
            body.agent_name,
            body.number,
        )
        return {"ok": True}

    # MCP の ASGI アプリをルートにマウントする（接続先は /mcp）
    # マウントは後続の全パスを引き受けるため、自前のルート登録より後に行う
    app.mount("/", mcp_app)
    return app
