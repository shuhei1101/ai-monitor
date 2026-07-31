"""「プロセス死活監視」の結合テスト（実プロセスを起動して確認する）。

エージェントも GitHub も登場しないため、E2E ハーネスではなく実プロセスの起動 / 停止で検証する。
モニターと監視役の代わりに、pid と最終周回時刻を書き続けるだけの軽量プロセスを立てる。
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import yaml

from ai_monitor.features.watchdog.restarts import record_restart
from ai_monitor.features.watchdog.service import check_liveness, supervise
from ai_monitor.features.watchdog.types import WatchTarget
from ai_monitor.integrations.process.ops import is_pid_alive, start_detached, terminate
from ai_monitor.shared.settings import WatchdogSettings

# 相手プロセスの代役（pid ファイルの場所を受け取り、周回時刻を書き続ける）
STAND_IN = (
    "import sys, time, datetime;"
    "p = sys.argv[1];"
    "[open(p, 'w').write(datetime.datetime.now(datetime.timezone.utc).isoformat()) or time.sleep(0.2)"
    " for _ in iter(int, 1)]"
)

# 実プロセスの起動 / 終了を待つ上限（秒）
WAIT_SEC = 10


def _wait_until(predicate) -> bool:
    """条件が真になるまで短い間隔で待つ。"""
    deadline = time.time() + WAIT_SEC
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def _pid_of(target: WatchTarget) -> int:
    """pid ファイルの内容を返す。"""
    return int(target.pid_path.read_text(encoding="utf-8"))


@pytest.fixture
def wd_settings(tmp_path) -> WatchdogSettings:
    """記録先を一時ディレクトリに向けた設定を返す。"""
    return WatchdogSettings(restarts_path=str(tmp_path / "restarts.yaml"), liveness_timeout_sec=5)


@pytest.fixture
def target_factory(tmp_path):
    """代役プロセスを起動する監視対象を作る factory を返す（テスト後に停止する）。"""
    created: list[WatchTarget] = []

    def _create(name: str, event: str) -> WatchTarget:
        beat_path = tmp_path / f"{name}.heartbeat"
        target = WatchTarget(
            name=name,
            pid_path=tmp_path / f"{name}.pid",
            heartbeat_path=beat_path,
            # 代役は待受を持たないので pid と鮮度だけで判定する
            port=None,
            start_command=[sys.executable, "-c", STAND_IN, str(beat_path)],
            down_event=event,
            log_path=tmp_path / f"{name}.log",
        )
        created.append(target)
        return target

    yield _create
    # 残った代役プロセスを片付ける
    for target in created:
        try:
            pid = _pid_of(target)
        except (OSError, ValueError):
            continue
        subprocess.run(["kill", "-9", str(pid)], capture_output=True, check=False)


@pytest.fixture
def notify_spy():
    """契機通知を記録するスパイを返す。"""
    state = NS(calls=[], result=None)

    def _notify(event, title, body, **kwargs):
        state.calls.append((event, title, body))
        return state.result

    state.notify = _notify
    return state


def _run(target: WatchTarget, wd_settings: WatchdogSettings, notify_spy) -> None:
    """実プロセスの操作で 1 周期分の監視を実行する。"""
    now = datetime.now(timezone.utc)
    supervise(
        target,
        now=now,
        settings=wd_settings,
        check=lambda t: check_liveness(
            t,
            now=now,
            timeout_sec=wd_settings.liveness_timeout_sec,
            is_pid_alive=is_pid_alive,
            can_connect=lambda port: True,
        ),
        start=start_detached,
        stop=terminate,
        notify=notify_spy.notify,
    )


def test_normal(target_factory, wd_settings, notify_spy):
    """落ちたモニターが実際に再起動されることを確認する（正常系）。"""
    # 準備: 代役を起動してから外部から落とす
    target = target_factory("monitor", "monitor_down")
    start_detached(target)
    first_pid = _pid_of(target)
    assert _wait_until(target.heartbeat_path.exists), "代役が周回時刻を書いていない"
    subprocess.run(["kill", "-9", str(first_pid)], check=True)
    assert _wait_until(lambda: not is_pid_alive(first_pid)), "代役が終了していない"
    # 実行
    _run(target, wd_settings, notify_spy)
    # 検証: 別の pid で動き直しており、記録と通知が残る
    second_pid = _pid_of(target)
    assert second_pid != first_pid
    assert is_pid_alive(second_pid) is True
    assert [e for e, _, _ in notify_spy.calls] == ["monitor_down"]
    entries = yaml.safe_load(Path(wd_settings.restarts_path).read_text(encoding="utf-8"))
    assert [e["name"] for e in entries] == ["monitor"]


def test_normal_when_limit_exceeded(target_factory, wd_settings, notify_spy):
    """上限に達していたら再起動しないことを確認する（正常系）。"""
    # 準備
    target = target_factory("monitor", "monitor_down")
    start_detached(target)
    first_pid = _pid_of(target)
    subprocess.run(["kill", "-9", str(first_pid)], check=True)
    assert _wait_until(lambda: not is_pid_alive(first_pid)), "代役が終了していない"
    path = Path(wd_settings.restarts_path)
    now = datetime.now(timezone.utc)
    for _ in range(wd_settings.restart_max):
        record_restart(path, "monitor", now=now, window_min=wd_settings.restart_window_min)
    # 実行
    _run(target, wd_settings, notify_spy)
    # 検証: pid ファイルが書き換わらず、記録も増えない
    assert _pid_of(target) == first_pid
    assert len(yaml.safe_load(path.read_text(encoding="utf-8"))) == wd_settings.restart_max
    assert str(wd_settings.restart_max) in notify_spy.calls[0][2]


def test_normal_when_watchdog_down(target_factory, wd_settings, notify_spy):
    """落ちた監視役が実際に再起動されることを確認する（正常系）。"""
    # 準備
    target = target_factory("watchdog", "watchdog_down")
    start_detached(target)
    first_pid = _pid_of(target)
    subprocess.run(["kill", "-9", str(first_pid)], check=True)
    assert _wait_until(lambda: not is_pid_alive(first_pid)), "代役が終了していない"
    # 実行
    _run(target, wd_settings, notify_spy)
    # 検証
    assert _pid_of(target) != first_pid
    assert [e for e, _, _ in notify_spy.calls] == ["watchdog_down"]


def test_normal_when_watchdog_limit_exceeded(target_factory, wd_settings, notify_spy):
    """監視役側も上限に達していたら再起動しないことを確認する（正常系）。"""
    # 準備
    target = target_factory("watchdog", "watchdog_down")
    start_detached(target)
    first_pid = _pid_of(target)
    subprocess.run(["kill", "-9", str(first_pid)], check=True)
    assert _wait_until(lambda: not is_pid_alive(first_pid)), "代役が終了していない"
    path = Path(wd_settings.restarts_path)
    now = datetime.now(timezone.utc)
    for _ in range(wd_settings.restart_max):
        record_restart(path, "watchdog", now=now, window_min=wd_settings.restart_window_min)
    # 実行
    _run(target, wd_settings, notify_spy)
    # 検証
    assert _pid_of(target) == first_pid
    assert [e for e, _, _ in notify_spy.calls] == ["watchdog_down"]
    assert len(yaml.safe_load(path.read_text(encoding="utf-8"))) == wd_settings.restart_max


def test_error_when_notify_failed(target_factory, wd_settings, notify_spy):
    """通知の送出に失敗しても再起動が完了することを確認する（異常系）。"""
    # 準備
    from ai_monitor.features.notify.types import SendResult

    notify_spy.result = SendResult(sent=False)
    target = target_factory("monitor", "monitor_down")
    start_detached(target)
    first_pid = _pid_of(target)
    subprocess.run(["kill", "-9", str(first_pid)], check=True)
    assert _wait_until(lambda: not is_pid_alive(first_pid)), "代役が終了していない"
    # 実行
    _run(target, wd_settings, notify_spy)
    # 検証
    second_pid = _pid_of(target)
    assert second_pid != first_pid
    assert is_pid_alive(second_pid) is True
