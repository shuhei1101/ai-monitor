"""監視役プロセスの composition root。"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from functools import partial

from ai_monitor.features.notify.service import build_notifier, build_settings_reader
from ai_monitor.features.watchdog.heartbeat import touch_heartbeat
from ai_monitor.features.watchdog.service import check_liveness, supervise
from ai_monitor.features.watchdog.types import Suspension
from ai_monitor.integrations.process.ops import can_connect, is_pid_alive, start_detached, terminate
from ai_monitor.observability import configure
from ai_monitor.shared.settings import Settings
from ai_monitor.features.watchdog.targets import build_monitor_target, build_watchdog_target

logger = logging.getLogger(__name__)


def main(*, cycles: int | None = None, sleep_fn=time.sleep) -> int:
    """設定を読み、モニターを対象にした監視を周期で実行する。"""
    # 設定と観測基盤を初期化する
    settings = Settings()
    configure("watchdog")
    # 自分の pid を書き出す（モニター側の生存確認が読む）
    self_target = build_watchdog_target(settings)
    self_target.pid_path.parent.mkdir(parents=True, exist_ok=True)
    self_target.pid_path.write_text(str(os.getpid()), encoding="utf-8")
    # モニターを対象にした監視対象と依存を組み立てる
    target = build_monitor_target(settings)
    notify = build_notifier(build_settings_reader(lambda: Settings().notifies))
    check = partial(
        check_liveness,
        timeout_sec=settings.watchdog.liveness_timeout_sec,
        is_pid_alive=is_pid_alive,
        can_connect=can_connect,
    )
    logger.info("監視役を起動しました: target=%s interval_sec=%s", target.name, settings.watchdog.interval_sec)
    # 打ち切りの状態はプロセスが生きている間だけ持つ（周期の外で 1 つ作って使い回す）
    suspensions: dict[str, Suspension] = {}
    # 周期でモニターを監視する
    remaining = cycles
    while remaining is None or remaining > 0:
        now = datetime.now(timezone.utc)
        try:
            # 自分の最終周回時刻を書いてからモニターを見る
            touch_heartbeat(self_target.heartbeat_path, now=now)
            supervise(
                target,
                now=now,
                settings=settings.watchdog,
                check=partial(check, now=now),
                start=start_detached,
                stop=terminate,
                notify=notify,
                suspensions=suspensions,
            )
        except Exception:
            # 周期を止めない（監視役が落ちると誰も気づけなくなる）
            logger.exception("監視の周期を見送りました: target=%s", target.name)
        if remaining is not None:
            remaining -= 1
        if remaining is None or remaining > 0:
            sleep_fn(settings.watchdog.interval_sec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
