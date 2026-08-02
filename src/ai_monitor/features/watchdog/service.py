"""相手プロセスの生存判定と、1 周期分の監視。"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from ai_monitor.features.notify.types import NotifyEvent, NotifyFn
from ai_monitor.features.watchdog.restarts import count_recent_restarts, record_restart
from ai_monitor.features.watchdog.types import (
    CanConnectFn,
    IsPidAliveFn,
    Liveness,
    StartProcessFn,
    StopProcessFn,
    Suspension,
    WatchTarget,
)
from ai_monitor.shared.settings import WatchdogSettings

logger = logging.getLogger(__name__)


def check_liveness(
    target: WatchTarget,
    *,
    now: datetime,
    timeout_sec: int,
    is_pid_alive: IsPidAliveFn,
    can_connect: CanConnectFn,
) -> Liveness:
    """3 つの材料から生存の可否を求める。"""
    # pid ファイルを読む（無い・読めない場合は停止とみなす）
    try:
        pid = int(target.pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return Liveness(alive=False, missing="pid ファイルが読めない")
    # pid の生存を確認する
    if not is_pid_alive(pid):
        return Liveness(alive=False, missing=f"pid {pid} が生きていない")
    # 待受ポートを持つ相手だけ接続を確認する
    if target.port is not None and not can_connect(target.port):
        return Liveness(alive=False, missing=f"ポート {target.port} が応答しない")
    # 最終周回時刻の鮮度を見る（無い・読めない場合も停止とみなす）
    try:
        beat = datetime.fromisoformat(target.heartbeat_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return Liveness(alive=False, missing="最終周回時刻が読めない", stale=True)
    elapsed = (now - beat).total_seconds()
    if elapsed > timeout_sec:
        return Liveness(alive=False, missing=f"最終周回時刻が {int(elapsed)} 秒前", stale=True)
    # 全て揃っていれば生存
    return Liveness(alive=True)


type CheckLivenessFn = Callable[[WatchTarget], Liveness]


def supervise(
    target: WatchTarget,
    *,
    now: datetime,
    settings: WatchdogSettings,
    check: CheckLivenessFn,
    start: StartProcessFn,
    stop: StopProcessFn,
    notify: NotifyFn,
    suspensions: dict[str, Suspension],
) -> None:
    """1 周期分の検知・再起動・通知を行う。"""
    # 相手の生存を求める
    liveness = check(target)
    # 生存している場合、打ち切り中だったときだけ復帰を知らせて状態を捨てる
    if liveness.alive:
        if suspensions.pop(target.name, None) is not None:
            logger.warning("打ち切っていた相手が復帰しました: target=%s", target.name)
            _notify(
                notify,
                target.recovered_event,
                f"{target.name} が復帰しました",
                f"{target.name} の生存を確認したため、再起動の打ち切りを解除しました。",
            )
        return
    # 期間内の再起動回数を数える
    path = Path(settings.restarts_path)
    count = count_recent_restarts(
        path, target.name, now=now, window_min=settings.restart_window_min
    )
    # 上限に達している場合、再起動せず通知の要否だけを判断する
    if count >= settings.restart_max:
        _notify_suspended(
            target,
            now=now,
            settings=settings,
            count=count,
            liveness=liveness,
            notify=notify,
            suspensions=suspensions,
        )
        return
    # 起動が失敗しても上限の勘定に入れるため、起動より前に記録する
    record_restart(path, target.name, now=now, window_min=settings.restart_window_min)
    # 周回だけが止まっている場合、pid が残ったまま二重起動しないよう先に停止する
    if liveness.stale:
        stop(target)
    # 相手を起動する（失敗しても監視は続ける）
    try:
        start(target)
    except Exception:
        logger.exception("相手の起動に失敗しました: target=%s", target.name)
        _notify(
            notify,
            target.down_event,
            f"{target.name} の再起動に失敗しました",
            f"理由: {liveness.missing}\n起動そのものが失敗しました。次の周期で再試行します。",
        )
        return
    logger.warning(
        "相手が停止したため再起動しました: target=%s missing=%s recent_restarts=%s",
        target.name,
        liveness.missing,
        count + 1,
    )
    _notify(
        notify,
        target.down_event,
        f"{target.name} が停止したため再起動しました",
        f"理由: {liveness.missing}\n"
        f"直近 {settings.restart_window_min} 分の再起動は {count + 1} 回目です（上限 {settings.restart_max} 回）。",
    )


def _notify_suspended(
    target: WatchTarget,
    *,
    now: datetime,
    settings: WatchdogSettings,
    count: int,
    liveness: Liveness,
    notify: NotifyFn,
    suspensions: dict[str, Suspension],
) -> None:
    """打ち切り中の通知を、打ち切りに入った最初と間隔を過ぎたときだけ送る。"""
    suspension = suspensions.get(target.name)
    # 打ち切りに入った最初の周期
    if suspension is None:
        logger.warning(
            "再起動の上限に達したため打ち切りました: target=%s window_min=%s restart_max=%s missing=%s",
            target.name,
            settings.restart_window_min,
            settings.restart_max,
            liveness.missing,
        )
        _notify(
            notify,
            target.down_event,
            f"{target.name} が停止しましたが再起動を打ち切りました",
            f"理由: {liveness.missing}\n"
            f"直近 {settings.restart_window_min} 分で {count} 回再起動しており、上限 {settings.restart_max} 回に達しています。",
        )
        suspensions[target.name] = Suspension(notified_at=now)
        return
    # 前回の通知から間隔が空いていなければ送らない（生存の確認は次の周期も続く）
    elapsed = now - suspension.notified_at
    if elapsed < timedelta(minutes=settings.suspended_notify_interval_min):
        return
    logger.warning(
        "再起動の打ち切りが続いています: target=%s elapsed_min=%s missing=%s",
        target.name,
        int(elapsed.total_seconds() // 60),
        liveness.missing,
    )
    _notify(
        notify,
        target.down_event,
        f"{target.name} が停止したままです",
        f"理由: {liveness.missing}\n"
        f"再起動は上限 {settings.restart_max} 回に達したため打ち切ったままです。",
    )
    suspensions[target.name] = Suspension(notified_at=now)


def _notify(notify: NotifyFn, event: NotifyEvent, title: str, body: str) -> None:
    """契機通知を送る（送出は補助手段なので失敗しても処理を止めない）。"""
    notify(event, title, body)
