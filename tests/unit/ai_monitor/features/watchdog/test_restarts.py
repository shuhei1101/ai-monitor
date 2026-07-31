"""`features/watchdog/restarts.py` の単体テスト。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import yaml

from ai_monitor.features.watchdog.restarts import count_recent_restarts, record_restart

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _write(path, entries) -> None:
    """記録ファイルを直接書く。"""
    path.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")


# ---- 直近の再起動回数 ----


def test_count_recent_restarts(tmp_path):
    """期間内の件数だけを数えることを確認する（正常系）。"""
    # 準備
    path = tmp_path / "restarts.yaml"
    _write(path, [
        {"name": "monitor", "at": (NOW - timedelta(minutes=10)).isoformat()},
        {"name": "monitor", "at": (NOW - timedelta(minutes=50)).isoformat()},
        {"name": "monitor", "at": (NOW - timedelta(minutes=90)).isoformat()},
    ])
    # 実行
    count = count_recent_restarts(path, "monitor", now=NOW, window_min=60)
    # 検証
    assert count == 2


def test_count_recent_restarts_when_other_target(tmp_path):
    """相手ごとに別勘定であることを確認する（正常系）。"""
    # 準備
    path = tmp_path / "restarts.yaml"
    _write(path, [
        {"name": "monitor", "at": NOW.isoformat()},
        {"name": "watchdog", "at": NOW.isoformat()},
        {"name": "watchdog", "at": NOW.isoformat()},
    ])
    # 実行
    count = count_recent_restarts(path, "watchdog", now=NOW, window_min=60)
    # 検証
    assert count == 2


def test_count_recent_restarts_when_file_missing(tmp_path):
    """記録ファイルが無いときに 0 を返すことを確認する（正常系）。"""
    # 実行
    count = count_recent_restarts(tmp_path / "none.yaml", "monitor", now=NOW, window_min=60)
    # 検証
    assert count == 0


def test_count_recent_restarts_when_broken(tmp_path):
    """記録が壊れているときに 0 を返すことを確認する（正常系）。"""
    # 準備
    path = tmp_path / "restarts.yaml"
    path.write_text("{ 壊れた: [", encoding="utf-8")
    # 実行
    count = count_recent_restarts(path, "monitor", now=NOW, window_min=60)
    # 検証
    assert count == 0


# ---- 再起動の記録 ----


def test_record_restart(tmp_path):
    """1 件の追記を確認する（正常系）。"""
    # 準備
    path = tmp_path / "restarts.yaml"
    _write(path, [{"name": "monitor", "at": (NOW - timedelta(minutes=5)).isoformat()}])
    # 実行
    record_restart(path, "monitor", now=NOW, window_min=60)
    # 検証
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[-1]["name"] == "monitor"
    assert datetime.fromisoformat(entries[-1]["at"]) == NOW


def test_record_restart_when_file_missing(tmp_path):
    """ファイルが無い状態からの記録を確認する（正常系）。"""
    # 準備
    path = tmp_path / "nested" / "restarts.yaml"
    # 実行
    record_restart(path, "watchdog", now=NOW, window_min=60)
    # 検証
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert [e["name"] for e in entries] == ["watchdog"]


def test_record_restart_when_expired(tmp_path):
    """保持期間を過ぎた記録が落ちることを確認する（正常系）。"""
    # 準備
    path = tmp_path / "restarts.yaml"
    _write(path, [{"name": "monitor", "at": (NOW - timedelta(minutes=300)).isoformat()}])
    # 実行
    record_restart(path, "monitor", now=NOW, window_min=60)
    # 検証
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert datetime.fromisoformat(entries[0]["at"]) == NOW
