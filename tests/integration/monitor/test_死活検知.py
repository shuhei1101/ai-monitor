"""「死活検知」の結合テスト。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import yaml

from ai_monitor.features.watchdog.restarts import record_restart
from ai_monitor.features.watchdog.service import check_liveness, supervise
from ai_monitor.features.watchdog.types import WatchTarget
from ai_monitor.shared.settings import WatchdogSettings

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def wd_settings(tmp_path) -> WatchdogSettings:
    """記録先を一時ディレクトリに向けた設定を返す。"""
    return WatchdogSettings(restarts_path=str(tmp_path / "restarts.yaml"))


@pytest.fixture
def target(tmp_path) -> WatchTarget:
    """モニターを指す監視対象を返す。"""
    return WatchTarget(
        name="monitor",
        pid_path=tmp_path / "monitor.pid",
        heartbeat_path=tmp_path / "monitor.heartbeat",
        port=8765,
        start_command=["true"],
        down_event="monitor_down",
    )


@pytest.fixture
def io_mocks():
    """プロセスの生存確認 / 起動 / 停止 / 通知の差し替えをまとめて返す。"""
    state = NS(alive=False, connect=True, started=[], stopped=[], notified=[], order=[], start_error=None)

    def _is_pid_alive(pid: int) -> bool:
        return state.alive

    def _can_connect(port: int) -> bool:
        return state.connect

    def _start(t: WatchTarget) -> None:
        state.order.append("start")
        if state.start_error is not None:
            raise state.start_error
        state.started.append(t.name)

    def _stop(t: WatchTarget) -> None:
        state.order.append("stop")
        state.stopped.append(t.name)

    def _notify(event, title, body, **kwargs):
        state.notified.append((event, title, body))
        return None

    state.is_pid_alive = _is_pid_alive
    state.can_connect = _can_connect
    state.start = _start
    state.stop = _stop
    state.notify = _notify
    return state


def _seed(target: WatchTarget, *, pid: int = 1234, beat_min_ago: int = 0) -> None:
    """生存材料のファイルを置く。"""
    target.pid_path.write_text(str(pid), encoding="utf-8")
    target.heartbeat_path.write_text(
        (NOW - timedelta(minutes=beat_min_ago)).isoformat(), encoding="utf-8"
    )


def _run(target: WatchTarget, wd_settings: WatchdogSettings, io_mocks) -> None:
    """生存判定から通知までを 1 周期分つなげて実行する。"""
    supervise(
        target,
        now=NOW,
        settings=wd_settings,
        check=lambda t: check_liveness(
            t,
            now=NOW,
            timeout_sec=wd_settings.liveness_timeout_sec,
            is_pid_alive=io_mocks.is_pid_alive,
            can_connect=io_mocks.can_connect,
        ),
        start=io_mocks.start,
        stop=io_mocks.stop,
        notify=io_mocks.notify,
    )


def test_normal(target, wd_settings, io_mocks):
    """停止の検知から記録・再起動・通知までを確認する（正常系）。"""
    # 準備
    _seed(target)
    io_mocks.alive = False
    # 実行
    _run(target, wd_settings, io_mocks)
    # 検証
    assert io_mocks.started == ["monitor"]
    assert [e for e, _, _ in io_mocks.notified] == ["monitor_down"]
    entries = yaml.safe_load(Path(wd_settings.restarts_path).read_text(encoding="utf-8"))
    assert [e["name"] for e in entries] == ["monitor"]


def test_normal_when_alive(target, wd_settings, io_mocks):
    """生存時に何も起きないことを確認する（正常系）。"""
    # 準備
    _seed(target)
    io_mocks.alive = True
    # 実行
    _run(target, wd_settings, io_mocks)
    # 検証
    assert (io_mocks.started, io_mocks.stopped, io_mocks.notified) == ([], [], [])
    assert not Path(wd_settings.restarts_path).exists()


def test_normal_when_stale(target, wd_settings, io_mocks):
    """周回が止まったときに停止してから起動することを確認する（正常系）。"""
    # 準備
    _seed(target, beat_min_ago=10)
    io_mocks.alive = True
    # 実行
    _run(target, wd_settings, io_mocks)
    # 検証
    assert io_mocks.order == ["stop", "start"], "pid が残ったまま二重起動している"
    assert "秒前" in io_mocks.notified[0][2], "通知に周回が止まった旨が入っていない"


def test_normal_when_limit_exceeded(target, wd_settings, io_mocks):
    """再起動の上限超過で通知だけを送ることを確認する（正常系）。"""
    # 準備
    _seed(target)
    io_mocks.alive = False
    path = Path(wd_settings.restarts_path)
    for _ in range(wd_settings.restart_max):
        record_restart(path, "monitor", now=NOW, window_min=wd_settings.restart_window_min)
    # 実行
    _run(target, wd_settings, io_mocks)
    # 検証
    assert io_mocks.started == []
    assert [e for e, _, _ in io_mocks.notified] == ["monitor_down"]
    assert len(yaml.safe_load(path.read_text(encoding="utf-8"))) == wd_settings.restart_max
    assert str(wd_settings.restart_max) in io_mocks.notified[0][2]


def test_error_when_notify_failed(target, wd_settings, io_mocks):
    """通知の送出に失敗しても再起動が完了することを確認する（異常系）。"""
    # 準備
    from ai_monitor.features.notify.types import SendResult

    _seed(target)
    io_mocks.alive = False
    io_mocks.notify = lambda event, title, body, **kwargs: SendResult(sent=False)
    # 実行
    _run(target, wd_settings, io_mocks)
    # 検証
    assert io_mocks.started == ["monitor"]


def test_error_when_start_failed(target, wd_settings, io_mocks):
    """起動そのものが失敗しても監視を続けられることを確認する（異常系）。"""
    # 準備
    _seed(target)
    io_mocks.alive = False
    io_mocks.start_error = OSError("起動できない")
    # 実行
    _run(target, wd_settings, io_mocks)
    # 検証
    assert io_mocks.started == []
    assert [e for e, _, _ in io_mocks.notified] == ["monitor_down"]
    entries = yaml.safe_load(Path(wd_settings.restarts_path).read_text(encoding="utf-8"))
    assert len(entries) == 1, "失敗が上限の勘定に入っていない"
