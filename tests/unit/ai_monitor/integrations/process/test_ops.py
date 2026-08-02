"""`integrations/process/ops.py` の単体テスト。"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from ai_monitor.features.watchdog.types import WatchTarget
from ai_monitor.integrations.process.ops import is_pid_alive, start_detached, terminate


@pytest.fixture
def target_factory(tmp_path):
    """一時ディレクトリを使う監視対象を作る factory を返す。"""

    def _create(*, command: list[str] | None = None):
        return WatchTarget(
            name="dummy",
            pid_path=tmp_path / "dummy.pid",
            heartbeat_path=tmp_path / "dummy.heartbeat",
            port=None,
            start_command=command or [sys.executable, "-c", "pass"],
            down_event="watchdog_down",
            recovered_event="watchdog_recovered",
            log_path=tmp_path / "dummy.log",
        )

    return _create


# ---- pid生存確認 ----


def test_is_pid_alive():
    """自プロセスの pid で真を返すことを確認する（正常系）。"""
    # 実行・検証
    assert is_pid_alive(os.getpid()) is True


def test_is_pid_alive_when_dead():
    """終了済みプロセスの pid で偽を返すことを確認する（正常系）。"""
    # 準備
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    # 実行・検証
    assert is_pid_alive(proc.pid) is False


# ---- 独立プロセス起動 ----


def test_start_detached(target_factory):
    """起動と pid / 最終周回時刻の書き出しを確認する（正常系）。"""
    # 準備
    target = target_factory()
    # 実行
    start_detached(target)
    # 検証
    pid = int(target.pid_path.read_text(encoding="utf-8"))
    assert pid > 0
    assert target.log_path.exists()
    # 起動直後を「周回が止まっている」と誤検知しないよう時刻を埋める
    assert target.heartbeat_path.exists(), "最終周回時刻が埋められていない"


def test_start_detached_when_command_missing(target_factory):
    """実行できないコマンドで例外を送出することを確認する（異常系）。"""
    # 準備
    target = target_factory(command=["ai-monitor-not-exist-command"])
    # 実行・検証
    with pytest.raises(OSError):
        start_detached(target)


# ---- プロセス停止 ----


def test_terminate(target_factory):
    """起動中のプロセスを停止することを確認する（正常系）。"""
    # 準備
    target = target_factory(command=[sys.executable, "-c", "import time; time.sleep(30)"])
    start_detached(target)
    pid = int(target.pid_path.read_text(encoding="utf-8"))
    # 実行
    terminate(target)
    # 検証
    for _ in range(50):
        if not is_pid_alive(pid):
            break
        time.sleep(0.1)
    assert is_pid_alive(pid) is False


def test_terminate_when_pid_missing(target_factory):
    """pid ファイルが無いときに何もしないことを確認する（正常系）。"""
    # 準備
    target = target_factory()
    # 実行・検証（例外を送出しない）
    terminate(target)
