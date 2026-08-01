"""モニターの FastAPI アプリ（MCP のマウント + ポーリングループの駆動）。"""
from __future__ import annotations

import logging
import os
import signal
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ai_monitor.features.agents.service import reset_session
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.config.service import reload_settings
from ai_monitor.features.config.types import BuildAgents, ReadSettings, ReloadResult
from ai_monitor.features.notify.types import NotifyFn
from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.features.rate_limit.service import resolve_reset_at
from ai_monitor.features.watchdog.heartbeat import touch_heartbeat
from ai_monitor.mcp.server import build_mcp_app
from ai_monitor.shared.settings import LabelSettings, Settings

if TYPE_CHECKING:
    from ai_monitor.features.sessions.registry import SessionRegistry

logger = logging.getLogger(__name__)


def _exit_process() -> None:
    """自プロセスへ終了シグナルを送る（uvicorn の停止手順を通す）。"""
    os.kill(os.getpid(), signal.SIGTERM)


class ContextResetRequest(BaseModel):
    """`POST /context_reset` のリクエストボディ。"""

    project: str
    agent_name: str
    number: int


class RateLimitRequest(BaseModel):
    """`POST /rate_limit` のリクエストボディ。"""

    project: str
    agent_name: str
    number: int
    transcript_path: str


def _default_build_agents(label_settings: LabelSettings) -> BuildAgents:
    """ラベル設定を束ねたエージェント組立関数を返す。"""

    def _build(settings: Settings) -> list[Agent]:
        # composition root への循環 import を避けるため呼び出し時に取り込む
        from ai_monitor.main import build_agents

        return build_agents(label_settings, agent_settings=settings.agents)

    return _build


def create_app(
    settings: Settings,
    *,
    registry: SessionRegistry,
    agents: list[Agent],
    label_settings: LabelSettings,
    notify: NotifyFn,
    heartbeat_path: Path | None = None,
    supervise_watchdog: Callable[[datetime], None] | None = None,
    exit_process: Callable[[], None] = _exit_process,
    read_settings: ReadSettings = Settings,
    build_agents: BuildAgents | None = None,
) -> FastAPI:
    """FastAPI アプリを生成し、MCP のマウントと lifespan を配線する。"""
    # 設定リロードで使うエージェント組立（指定が無ければラベル設定を束ねた既定を使う）
    build_agents_fn = build_agents if build_agents is not None else _default_build_agents(label_settings)
    # MCP サーバーの ASGI アプリを組み立てる
    mcp_app = build_mcp_app(settings, registry=registry, agents=agents, label_settings=label_settings)
    # 上限の待機状態は到達通知の受信とポーリングループで共有する（上限はアカウント単位なので 1 つだけ持つ）
    gate = RateLimitGate()

    # lifespan で MCP のセッション管理を開始し、その内側でポーリングループを起動する
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from ai_monitor.main import run_cycle

        stop = threading.Event()

        def loop() -> None:
            prev_targets: dict = {}
            heartbeat_at = "1970-01-01T00:00:00+00:00"
            # ループが例外で抜けたら理由を残してプロセスごと落とす
            # （HTTP だけ生きている状態にすると、MCP は応答するのに仕事が割り当てられなくなる）
            try:
                while not stop.is_set():
                    now = datetime.now(timezone.utc)
                    # 監視役が鮮度を見る材料として、1 周ごとに時刻を書く
                    if heartbeat_path is not None:
                        touch_heartbeat(heartbeat_path, now=now)
                    prev_targets, heartbeat_at = run_cycle(
                        settings,
                        agents,
                        registry=registry,
                        prev_targets=prev_targets,
                        last_heartbeat_at=heartbeat_at,
                        labels=label_settings,
                        gate=gate,
                        notify=notify,
                    )
                    # 監視役の生存を見る（落ちていれば再起動して通知する）
                    if supervise_watchdog is not None:
                        supervise_watchdog(now)
                    stop.wait(settings.poll_interval_sec)
            except BaseException:
                logger.critical("ポーリングループが停止したためプロセスを終了します", exc_info=True)
                exit_process()

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

    @app.post("/rate_limit")
    def receive_rate_limit(body: RateLimitRequest) -> dict:
        """上限到達の通知を受け、リセット時刻まで待機を開始する。"""
        # 台帳からセッションを検索する
        session = registry.find(body.project, body.agent_name, body.number)
        if session is None:
            logger.warning(
                "台帳に無いセッションからのレートリミット通知を拒否しました: "
                "project=%s agent_name=%s number=%s",
                body.project,
                body.agent_name,
                body.number,
            )
            raise HTTPException(status_code=404)
        # 会話ログからリセット時刻を読む（読めなければ既定の待機時間から算出する）
        now = datetime.now(timezone.utc).astimezone()
        resets_at = resolve_reset_at(Path(body.transcript_path), now)
        if resets_at is None:
            resets_at = now + timedelta(minutes=settings.rate_limit_fallback_min)
        # 解除時刻と対象セッションを関門に記録する
        gate.block(session.session_name, resets_at)
        logger.info(
            "レートリミットの待機を開始しました: session_name=%s resets_at=%s",
            session.session_name,
            resets_at.isoformat(),
        )
        notify(
            "rate_limit",
            "Claude の利用上限に達しました",
            f"セッション: {session.session_name}\nリセット: {resets_at.isoformat()}",
        )
        return {"resets_at": resets_at.isoformat()}

    @app.post("/reload")
    def receive_reload() -> ReloadResult:
        """再読込要求を受け、稼働中の設定とエージェント定義を書き換える。"""
        # 読み直しの失敗は理由を添えて 500 で返す（稼働中の設定は書き換わっていない）
        try:
            return reload_settings(
                settings, agents, read_settings=read_settings, build_agents=build_agents_fn
            )
        except Exception as exc:
            logger.error("設定を読み直せませんでした: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"設定を読み直せませんでした: {exc}"
            ) from exc

    # MCP の ASGI アプリをルートにマウントする（接続先は /mcp）
    # マウントは後続の全パスを引き受けるため、自前のルート登録より後に行う
    app.mount("/", mcp_app)
    return app
