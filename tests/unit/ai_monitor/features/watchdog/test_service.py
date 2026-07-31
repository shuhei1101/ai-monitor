"""`features/watchdog/service.py` の単体テスト。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_monitor.features.watchdog.service import check_liveness, supervise
from ai_monitor.features.watchdog.types import Liveness, WatchTarget
from ai_monitor.shared.settings import WatchdogSettings

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def target_factory(tmp_path):
    """生存材料のファイルを置いた監視対象を作る factory を返す。"""

    def _create(*, pid: int | None = 1234, beat_min_ago: int | None = 0, port: int | None = 8765):
        pid_path = tmp_path / "target.pid"
        beat_path = tmp_path / "target.heartbeat"
        if pid is not None:
            pid_path.write_text(str(pid), encoding="utf-8")
        if beat_min_ago is not None:
            beat_path.write_text((NOW - timedelta(minutes=beat_min_ago)).isoformat(), encoding="utf-8")
        return WatchTarget(
            name="monitor",
            pid_path=pid_path,
            heartbeat_path=beat_path,
            port=port,
            start_command=["true"],
            down_event="monitor_down",
        )

    return _create


@pytest.fixture
def spies():
    """呼び出しを記録するスパイ関数群を返す。"""
    from types import SimpleNamespace as NS

    state = NS(started=[], stopped=[], notified=[], order=[])

    def _start(target):
        state.started.append(target.name)
        state.order.append("start")

    def _stop(target):
        state.stopped.append(target.name)
        state.order.append("stop")

    def _notify(event, title, body, **kwargs):
        state.notified.append((event, title, body))
        return None

    state.start = _start
    state.stop = _stop
    state.notify = _notify
    return state


# ---- 生存判定 ----


def test_check_liveness(target_factory):
    """全材料が揃った生存を確認する（正常系）。"""
    # 準備
    target = target_factory()
    # 実行
    result = check_liveness(
        target, now=NOW, timeout_sec=120, is_pid_alive=lambda pid: True, can_connect=lambda port: True
    )
    # 検証
    assert result.alive is True


def test_check_liveness_when_pid_missing(target_factory):
    """pid ファイルが無いときに停止と判定することを確認する（正常系）。"""
    # 準備
    target = target_factory(pid=None)
    calls: list[int] = []
    # 実行
    result = check_liveness(
        target, now=NOW, timeout_sec=120, is_pid_alive=lambda pid: True,
        can_connect=lambda port: calls.append(port) or True,
    )
    # 検証
    assert result.alive is False
    assert not calls, "pid が読めない時点で接続確認まで進んでいる"


def test_check_liveness_when_pid_dead(target_factory):
    """pid が死んでいるときの判定を確認する（正常系）。"""
    # 準備
    target = target_factory()
    # 実行
    result = check_liveness(
        target, now=NOW, timeout_sec=120, is_pid_alive=lambda pid: False, can_connect=lambda port: True
    )
    # 検証
    assert (result.alive, result.stale) == (False, False)


def test_check_liveness_when_port_closed(target_factory):
    """待受が応答しないときの判定を確認する（正常系）。"""
    # 準備
    target = target_factory()
    # 実行
    result = check_liveness(
        target, now=NOW, timeout_sec=120, is_pid_alive=lambda pid: True, can_connect=lambda port: False
    )
    # 検証
    assert (result.alive, result.stale) == (False, False)


def test_check_liveness_when_stale(target_factory):
    """最終周回時刻が古いときの判定を確認する（正常系）。"""
    # 準備
    target = target_factory(beat_min_ago=10)
    # 実行
    result = check_liveness(
        target, now=NOW, timeout_sec=120, is_pid_alive=lambda pid: True, can_connect=lambda port: True
    )
    # 検証
    assert (result.alive, result.stale) == (False, True)


def test_check_liveness_when_no_port(target_factory):
    """待受ポートを持たない相手の判定を確認する（正常系）。"""
    # 準備
    target = target_factory(port=None)
    calls: list[int] = []
    # 実行
    result = check_liveness(
        target, now=NOW, timeout_sec=120, is_pid_alive=lambda pid: True,
        can_connect=lambda port: calls.append(port) or True,
    )
    # 検証
    assert result.alive is True
    assert not calls, "ポートを持たない相手で接続確認が呼ばれている"


# ---- 監視 ----


@pytest.fixture
def wd_settings(tmp_path):
    """記録先を一時ディレクトリに向けた設定を返す。"""
    return WatchdogSettings(restarts_path=str(tmp_path / "restarts.yaml"))


def test_supervise(target_factory, spies, wd_settings):
    """停止の検知から再起動と通知までを確認する（正常系）。"""
    # 準備
    target = target_factory()
    # 実行
    supervise(
        target, now=NOW, settings=wd_settings, check=lambda t: Liveness(alive=False, missing="pid 停止"),
        start=spies.start, stop=spies.stop, notify=spies.notify,
    )
    # 検証
    assert spies.started == ["monitor"]
    assert [e for e, _, _ in spies.notified] == ["monitor_down"]
    import pathlib

    from ai_monitor.features.watchdog.restarts import count_recent_restarts

    assert count_recent_restarts(
        pathlib.Path(wd_settings.restarts_path), "monitor", now=NOW, window_min=60
    ) == 1


def test_supervise_when_alive(target_factory, spies, wd_settings):
    """生存時に何もしないことを確認する（正常系）。"""
    # 準備
    target = target_factory()
    # 実行
    supervise(
        target, now=NOW, settings=wd_settings, check=lambda t: Liveness(alive=True),
        start=spies.start, stop=spies.stop, notify=spies.notify,
    )
    # 検証
    assert (spies.started, spies.stopped, spies.notified) == ([], [], [])


def test_supervise_when_stale(target_factory, spies, wd_settings):
    """周回だけが止まったときに停止してから起動することを確認する（正常系）。"""
    # 準備
    target = target_factory()
    # 実行
    supervise(
        target, now=NOW, settings=wd_settings,
        check=lambda t: Liveness(alive=False, missing="周回停止", stale=True),
        start=spies.start, stop=spies.stop, notify=spies.notify,
    )
    # 検証
    assert spies.order == ["stop", "start"], "pid が残ったまま二重起動している"


def test_supervise_when_limit_exceeded(target_factory, spies, wd_settings):
    """再起動の上限超過を確認する（正常系）。"""
    # 準備
    import pathlib

    from ai_monitor.features.watchdog.restarts import record_restart

    path = pathlib.Path(wd_settings.restarts_path)
    for _ in range(wd_settings.restart_max):
        record_restart(path, "monitor", now=NOW, window_min=wd_settings.restart_window_min)
    target = target_factory()
    # 実行
    supervise(
        target, now=NOW, settings=wd_settings, check=lambda t: Liveness(alive=False, missing="pid 停止"),
        start=spies.start, stop=spies.stop, notify=spies.notify,
    )
    # 検証
    assert spies.started == []
    assert [e for e, _, _ in spies.notified] == ["monitor_down"]
    import yaml

    assert len(yaml.safe_load(path.read_text(encoding="utf-8"))) == wd_settings.restart_max


def test_supervise_when_start_failed(target_factory, spies, wd_settings):
    """起動そのものが失敗したときの扱いを確認する（正常系）。"""
    # 準備
    import pathlib

    from ai_monitor.features.watchdog.restarts import count_recent_restarts

    def _start(target):
        raise OSError("起動できない")

    target = target_factory()
    # 実行
    supervise(
        target, now=NOW, settings=wd_settings, check=lambda t: Liveness(alive=False, missing="pid 停止"),
        start=_start, stop=spies.stop, notify=spies.notify,
    )
    # 検証
    assert [e for e, _, _ in spies.notified] == ["monitor_down"]
    assert count_recent_restarts(
        pathlib.Path(wd_settings.restarts_path), "monitor", now=NOW, window_min=60
    ) == 1, "失敗が上限の勘定に入っていない"


def test_supervise_when_notify_failed(target_factory, spies, wd_settings):
    """通知の送出に失敗しても再起動が完了することを確認する（正常系）。"""
    # 準備
    from ai_monitor.features.notify.types import SendResult

    calls: list[str] = []

    def _notify(event, title, body, **kwargs):
        calls.append(event)
        return SendResult(sent=False)

    target = target_factory()
    # 実行
    supervise(
        target, now=NOW, settings=wd_settings, check=lambda t: Liveness(alive=False, missing="pid 停止"),
        start=spies.start, stop=spies.stop, notify=_notify,
    )
    # 検証
    assert spies.started == ["monitor"]
    assert calls == ["monitor_down"]
