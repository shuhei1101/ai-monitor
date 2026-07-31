"""監視対象の組み立て（モニターと監視役の両プロセスが同じ定義を使う）。"""
from __future__ import annotations

import sys
from pathlib import Path

from ai_monitor.features.watchdog.types import WatchTarget
from ai_monitor.shared.settings import Settings

# 生存材料と起動ログの置き場所（状態ファイルと同じディレクトリに揃える）
MONITOR_NAME = "monitor"
WATCHDOG_NAME = "watchdog"


def _data_dir(settings: Settings) -> Path:
    """生存材料を置くディレクトリを返す。"""
    return Path(settings.state_path).parent


def build_monitor_target(settings: Settings) -> WatchTarget:
    """監視役が見るモニターの監視対象を組み立てる。"""
    base = _data_dir(settings)
    return WatchTarget(
        name=MONITOR_NAME,
        pid_path=base / f"{MONITOR_NAME}.pid",
        heartbeat_path=base / f"{MONITOR_NAME}.heartbeat",
        # モニターは待受を持つのでハングも検知できる
        port=settings.port,
        start_command=[sys.executable, "-m", "ai_monitor"],
        down_event="monitor_down",
        log_path=base / f"{MONITOR_NAME}.log",
    )


def build_watchdog_target(settings: Settings) -> WatchTarget:
    """モニターが見る監視役の監視対象を組み立てる。"""
    base = _data_dir(settings)
    return WatchTarget(
        name=WATCHDOG_NAME,
        pid_path=base / f"{WATCHDOG_NAME}.pid",
        heartbeat_path=base / f"{WATCHDOG_NAME}.heartbeat",
        # 監視役は待受を持たないので pid と鮮度だけで見る
        port=None,
        start_command=[sys.executable, "-m", "ai_monitor.watchdog"],
        down_event="watchdog_down",
        log_path=base / f"{WATCHDOG_NAME}.log",
    )
