"""`watchdog/__main__.py` の単体テスト。"""
from __future__ import annotations

import os

import pytest

import ai_monitor.watchdog.__main__ as wd_main
from ai_monitor.shared.settings import WatchdogSettings


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """設定と依存を差し替え、監視の呼び出しを記録する。"""
    from types import SimpleNamespace as NS

    state = NS(supervised=[], beats=[], suspensions=[])
    settings = NS(
        state_path=str(tmp_path / "state.yaml"),
        port=8765,
        notifies=[],
        watchdog=WatchdogSettings(restarts_path=str(tmp_path / "restarts.yaml")),
    )
    monkeypatch.setattr(wd_main, "Settings", lambda: settings)
    monkeypatch.setattr(wd_main, "configure", lambda name: None)
    monkeypatch.setattr(wd_main, "build_settings_reader", lambda read: read)
    monkeypatch.setattr(wd_main, "build_notifier", lambda read: (lambda *a, **k: None))
    monkeypatch.setattr(
        wd_main, "touch_heartbeat", lambda path, *, now: state.beats.append(path)
    )
    def _supervise(target, **kwargs):
        state.supervised.append(target.name)
        state.suspensions.append(kwargs.get("suspensions"))

    monkeypatch.setattr(wd_main, "supervise", _supervise)
    state.settings = settings
    return state


def test_main(wired):
    """1 周期の実行と pid の書き出しを確認する（正常系）。"""
    # 実行
    code = wd_main.main(cycles=1, sleep_fn=lambda sec: None)
    # 検証
    assert code == 0
    assert wired.supervised == ["monitor"]
    assert wired.beats, "自分の最終周回時刻が書かれていない"
    assert wired.suspensions == [{}], "打ち切り状態の台帳が渡っていない"
    pid_path = __import__("pathlib").Path(wired.settings.state_path).parent / "watchdog.pid"
    assert int(pid_path.read_text(encoding="utf-8")) == os.getpid()


def test_main_when_multiple_cycles(wired):
    """複数周期で打ち切り状態の台帳が引き継がれることを確認する（正常系）。"""
    # 実行
    code = wd_main.main(cycles=2, sleep_fn=lambda sec: None)
    # 検証
    assert code == 0
    assert len(wired.suspensions) == 2
    assert wired.suspensions[0] is wired.suspensions[1], "周期ごとに台帳が作り直されている"


def test_main_when_cycle_failed(wired, monkeypatch):
    """周期内の例外で監視役が落ちないことを確認する（正常系）。"""
    # 準備
    def _raise(target, **kwargs):
        raise RuntimeError("周期の失敗")

    monkeypatch.setattr(wd_main, "supervise", _raise)
    # 実行
    code = wd_main.main(cycles=2, sleep_fn=lambda sec: None)
    # 検証
    assert code == 0, "例外が伝播して監視役が落ちている"
