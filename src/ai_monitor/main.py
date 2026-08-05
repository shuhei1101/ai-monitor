"""composition root（設定読込・配線・起動）。"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import uvicorn

from ai_monitor.features.agents.service import poll
from ai_monitor.features.agents.types import Agent
from ai_monitor.features.cleanup.service import (
    close_completed_intakes,
    reap_timed_out_sessions,
    release_closed_roots,
    release_closed_sessions,
)
from ai_monitor.features.health.service import check_dependencies
from ai_monitor.features.notify.gates import notify_open_gates
from ai_monitor.features.notify.types import NotifyFn
from ai_monitor.features.rate_limit.gate import RateLimitGate
from ai_monitor.features.rate_limit.service import resume_blocked_sessions
from ai_monitor.features.notify.service import build_notifier, build_settings_reader
from ai_monitor.features.sessions.registry import SessionRegistry
from ai_monitor.features.watchdog.service import check_liveness, supervise
from ai_monitor.features.watchdog.targets import build_monitor_target, build_watchdog_target
from ai_monitor.features.watchdog.types import Liveness, StartProcessFn, Suspension, WatchTarget
from ai_monitor.integrations.process.ops import can_connect, is_pid_alive, start_detached, terminate
from ai_monitor.integrations.github.client import check_github, get_client
from ai_monitor.integrations.webhook.client import check_webhook
from ai_monitor.integrations.github.search import list_open_targets
from ai_monitor.observability import configure
from ai_monitor.server.app import create_app
from ai_monitor.server.listen import bind_listen_socket
from ai_monitor.shared.settings import _AGENT_NAMES, AgentSettings, LabelSettings, Settings
from ai_monitor.shared.types import MonitorTarget

logger = logging.getLogger(__name__)

_STANDALONE_NAMES = {"epic-poc-runner", "library-poc-runner", "resetter", "questioner"}


def build_agents(labels: LabelSettings, *, agent_settings: dict[str, AgentSettings]) -> list[Agent]:
    """全エージェントの Agent をラベル設定と agent_settings の値から組み立てる。"""
    agents = []
    for name in _AGENT_NAMES:
        field = name.replace("-", "_")
        # 確認 / 処理中ラベル + モデル + 推論労力を取り出して組み立てる（独立系 5 種は standalone=True）
        agents.append(
            Agent(
                name=name,
                confirm_label=getattr(labels, f"confirm_{field}"),
                processing_label=getattr(labels, f"processing_{field}"),
                model=agent_settings[name].model,
                effort=agent_settings[name].effort,
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
    labels: LabelSettings,
    gate: RateLimitGate,
    notified_gates: dict[str, set[int]],
    notify: NotifyFn,
) -> tuple[dict[str, list[MonitorTarget]], str]:
    """ポーリング + クリーンアップ検知 + heartbeat 判定の 1 周期を実行する。"""
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
                poll(
                    project,
                    agent,
                    targets,
                    registry=registry,
                    telemetry=settings.telemetry,
                    port=settings.port,
                    ai_monitor_wiki_base=settings.ai_monitor_wiki_base,
                    priority_urgent=labels.priority_urgent,
                    priority_low=labels.priority_low,
                    gate=gate,
                )
            # ユーザーの番になった対象を通知する（開いたゲートごとに 1 度だけ）
            notify_open_gates(
                targets,
                notified=notified_gates.setdefault(project.name, set()),
                project=project.name,
                discussion_label=labels.in_discussion,
                confirm_prefix=labels.confirm_prefix,
                repo=project.repo,
                notify=notify,
            )
            # クリーンアップ検知を実行する
            close_completed_intakes(
                project,
                targets,
                prev_targets.get(project.name, []),
                intake_label=labels.layer_intake,
            )
            release_closed_roots(
                project,
                targets,
                prev_targets.get(project.name, []),
                registry=registry,
                confirm_prefix=labels.confirm_prefix,
                notify=notify,
            )
            release_closed_sessions(project, targets, registry=registry, agents=agents)
            # heartbeat 間隔が経過していれば再開送信 → タイムアウト回収の順に実行する
            # （逆順だと待機で古くなった last_seen_at を回収が拾い、再開直後のセッションを kill する）
            if heartbeat_elapsed:
                resume_blocked_sessions(gate, registry=registry, now=now)
                reap_timed_out_sessions(
                    project,
                    targets,
                    registry=registry,
                    agents=agents,
                    timeout_min=settings.session_timeout_min,
                    gate=gate,
                    notify=notify,
                )
        except Exception:
            logger.exception("プロジェクトの周期を見送ります: project=%s", project.name)
            targets_by_project.pop(project.name, None)
    if heartbeat_elapsed:
        last_heartbeat_at = now.isoformat()
    return targets_by_project, last_heartbeat_at


def main() -> int:
    """設定読込 → 依存確認 → 台帳復元 → FastAPI アプリ起動を行う。"""
    settings = Settings()
    labels = LabelSettings()
    get_client(settings)
    configure("monitor")
    # 外部 API へ疎通し、必須依存が繋がらなければ起動しない
    results = check_dependencies(
        settings.notifies, check_github_fn=check_github, check_webhook_fn=check_webhook
    )
    blocked = [r for r in results if r.required and not r.ok]
    if blocked:
        logger.error(
            "必須依存へ繋がらないため起動を中止します: %s",
            " / ".join(f"{r.name}: {r.reason}" for r in blocked),
        )
        return 1
    agents = build_agents(labels, agent_settings=settings.agents)
    registry = SessionRegistry(Path(settings.state_path))
    # 待受ポートを先に確定させる（監視対象・MCP 接続先・フックの送信先が確定値を使うため）
    port_path = Path(settings.state_path).parent / "monitor.port"
    try:
        listen_socket = bind_listen_socket(settings, port_path)
    except OSError as exc:
        logger.error("待受ポートを確保できないため起動を中止します: port=%s reason=%s", settings.port, exc)
        return 1
    logger.info(
        "モニターを起動します: env=%s port=%s projects=%s",
        os.environ.get("AI_MONITOR_ENV", "(既定)"),
        settings.port,
        [p.repo for p in settings.projects],
    )
    # 自分の pid を書き出す（監視役の生存確認が読む）
    self_target = build_monitor_target(settings)
    self_target.pid_path.parent.mkdir(parents=True, exist_ok=True)
    self_target.pid_path.write_text(str(os.getpid()), encoding="utf-8")
    # 監視役の監視を組み立て、居なければ起動する（無効なら監視も起動もしない）
    watchdog_target = build_watchdog_target(settings)
    check = partial(
        check_liveness,
        timeout_sec=settings.watchdog.liveness_timeout_sec,
        is_pid_alive=is_pid_alive,
        can_connect=can_connect,
    )
    # 送出のたびに設定を読み直す（Webhook の変更に再起動を要らなくする）
    notify = build_notifier(build_settings_reader(lambda: Settings().notifies))
    if settings.watchdog.enabled:
        ensure_watchdog_started(
            watchdog_target,
            now=datetime.now(timezone.utc),
            check=partial(check, now=datetime.now(timezone.utc)),
            start=start_detached,
        )

    # 打ち切りの状態はプロセスが生きている間だけ持つ（周期をまたいで同じものを渡す）
    watchdog_suspensions: dict[str, Suspension] = {}

    def _supervise_watchdog(now: datetime) -> None:
        """監視役の生存を 1 周期分見る。"""
        supervise(
            watchdog_target,
            now=now,
            settings=settings.watchdog,
            check=partial(check, now=now),
            start=start_detached,
            stop=terminate,
            notify=notify,
            suspensions=watchdog_suspensions,
        )

    app = create_app(
        settings,
        registry=registry,
        agents=agents,
        label_settings=labels,
        notify=notify,
        heartbeat_path=self_target.heartbeat_path,
        supervise_watchdog=_supervise_watchdog if settings.watchdog.enabled else None,
    )
    uvicorn.Server(uvicorn.Config(app)).run(sockets=[listen_socket])
    return 0


def ensure_watchdog_started(
    target: WatchTarget, *, now: datetime, check: Callable[[WatchTarget], Liveness], start: StartProcessFn
) -> None:
    """モニターの起動時に、監視役が動いていなければ起動する。"""
    # 監視役に再起動されたモニターは、既に動いている監視役に相乗りする
    if check(target).alive:
        return
    # 起動時は通知も記録もしない（正常な起動でも監視役は必ず居ないため誤検知になる）
    try:
        start(target)
    except Exception:
        # 監視が無い状態にはなるが、ワークフロー自体は回るのでモニターは続ける
        logger.exception("監視役の起動に失敗しました: target=%s", target.name)
        return
    logger.info("監視役を起動しました: start_command=%s", target.start_command)


if __name__ == "__main__":
    raise SystemExit(main())
