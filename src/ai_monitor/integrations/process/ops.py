"""プロセスの実体操作（OS へ問い合わせる薄い層）。"""
from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ai_monitor.features.watchdog.heartbeat import touch_heartbeat
from ai_monitor.features.watchdog.types import WatchTarget

logger = logging.getLogger(__name__)

# 待受ポートの応答確認に使うタイムアウト（秒）
CONNECT_TIMEOUT_SEC = 2


def is_pid_alive(pid: int) -> bool:
    """pid が生きているかを OS へ問い合わせる。"""
    try:
        # シグナル 0 は送信せず存在確認だけを行う
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 権限が無いだけでプロセスは存在する
        return True
    # 終了済みで親に回収されていない子（ゾンビ）は存在するが動いていない
    return not _is_zombie(pid)


def _is_zombie(pid: int) -> bool:
    """プロセスがゾンビ状態かを返す。"""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        # /proc を持たない環境では判定材料が無いので、動いている扱いにする
        return False
    # 実行ファイル名に空白や括弧が入りうるので、閉じ括弧の後ろから状態を取る
    _, _, rest = stat.rpartition(")")
    return rest.strip().startswith("Z")


def can_connect(port: int) -> bool:
    """待受ポートへ繋がるかを返す。"""
    try:
        socket.create_connection(("127.0.0.1", port), timeout=CONNECT_TIMEOUT_SEC).close()
    except OSError:
        return False
    return True


def start_detached(target: WatchTarget) -> None:
    """親の終了に巻き込まれない子プロセスを起動し、pid を書き出す。"""
    # 落ちた理由の記録が再起動で消えないよう追記で開く
    if target.log_path is not None:
        target.log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = target.log_path.open("a", encoding="utf-8")
    else:
        stream = subprocess.DEVNULL
    try:
        # 新しいセッションで起動する（親と同じプロセスグループだと道連れになる）
        proc = subprocess.Popen(
            target.start_command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
        )
    finally:
        if target.log_path is not None:
            stream.close()
    # 起動した pid を書き出す
    target.pid_path.parent.mkdir(parents=True, exist_ok=True)
    target.pid_path.write_text(str(proc.pid), encoding="utf-8")
    # 起動時刻で最終周回時刻を埋めておく
    # （相手が最初の周回を書くまでの間、鮮度の閾値ぶんの猶予を与えて起動直後の誤検知を防ぐ）
    touch_heartbeat(target.heartbeat_path, now=datetime.now(timezone.utc))
    logger.info("プロセスを起動しました: target=%s pid=%s", target.name, proc.pid)


def terminate(target: WatchTarget) -> None:
    """pid ファイルの pid へ終了シグナルを送る。"""
    try:
        pid = int(target.pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        # 読めなければ止める相手が分からないので何もしない
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        # 既に終了している場合は何もしない
        return
    logger.info("プロセスを停止しました: target=%s pid=%s", target.name, pid)
