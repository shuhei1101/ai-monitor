"""死活監視ドメインの型定義。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_monitor.features.notify.types import NotifyEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class WatchTarget:
    """監視する相手 1 つ分の識別子と、生存材料の在りか。"""

    name: str
    pid_path: Path
    heartbeat_path: Path
    start_command: list[str]
    # 停止を知らせる契機（対象で変わる）
    down_event: NotifyEvent
    # 応答確認に使うポート。None なら接続確認をしない（監視役が対象のとき）
    port: int | None = None
    # 標準出力と標準エラーの追記先（落ちた理由を残すため上書きしない）
    log_path: Path | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Liveness:
    """生存の可否と、判定の根拠。"""

    alive: bool
    # 最初に欠けた材料の説明（生存時は空文字）
    missing: str = ""
    # 鮮度だけが欠けたか（起動前に停止が要るかの判断に使う）
    stale: bool = False


# pid の生存を返す関数
type IsPidAliveFn = Callable[[int], bool]

# 待受ポートへ繋がるかを返す関数
type CanConnectFn = Callable[[int], bool]

# 相手を起動する関数
type StartProcessFn = Callable[[WatchTarget], None]

# 相手を停止する関数
type StopProcessFn = Callable[[WatchTarget], None]
