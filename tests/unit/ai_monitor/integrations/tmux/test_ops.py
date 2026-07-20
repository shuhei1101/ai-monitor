"""`src/ai_monitor/integrations/tmux/ops.py` の単体テスト。"""
from __future__ import annotations

import subprocess
import time

import pytest

import ai_monitor.integrations.tmux.ops as ops


def test_create_session(tmp_session_name, tmp_path):
    """detached 作成を確認する（正常系）。"""
    # 実行
    ops.create_session(tmp_session_name, str(tmp_path))
    # 検証
    assert ops.has_session(tmp_session_name) is True


def test_create_session_when_duplicate_name(tmp_tmux_session, tmp_path):
    """同名セッションの重複作成を確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        ops.create_session(tmp_tmux_session, str(tmp_path))


def test_send_keys(tmp_tmux_session):
    """文字列の送信と実行を確認する（正常系）。"""
    # 実行
    ops.send_keys(tmp_tmux_session, "echo pytest-marker")
    # 検証
    time.sleep(0.5)
    captured = subprocess.run(
        ["tmux", "capture-pane", "-t", tmp_tmux_session, "-p"], capture_output=True, text=True, check=True
    )
    assert "pytest-marker" in captured.stdout


def test_send_keys_when_session_missing(tmp_session_name):
    """セッション不存在を確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        ops.send_keys(tmp_session_name, "echo x")


def test_has_session(tmp_tmux_session):
    """存在するセッションを確認する（正常系）。"""
    # 実行・検証
    assert ops.has_session(tmp_tmux_session) is True


def test_has_session_when_session_missing(tmp_session_name):
    """存在しないセッションを確認する（正常系）。"""
    # 実行・検証
    assert ops.has_session(tmp_session_name) is False


def test_kill_session(tmp_tmux_session):
    """kill の実行を確認する（正常系）。"""
    # 実行
    ops.kill_session(tmp_tmux_session)
    # 検証
    assert ops.has_session(tmp_tmux_session) is False


def test_kill_session_when_session_missing(tmp_session_name):
    """セッション不存在を確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        ops.kill_session(tmp_session_name)


def test_run_tmux():
    """tmux の実行を確認する（正常系）。"""
    # 実行
    result = ops._run_tmux(["-V"])
    # 検証
    assert result.returncode == 0
    assert result.stdout.startswith("tmux")


def test_run_tmux_when_check_false_nonzero(tmp_session_name):
    """`check=False` の非 0 許容を確認する（正常系）。"""
    # 実行
    result = ops._run_tmux(["has-session", "-t", tmp_session_name], check=False)
    # 検証
    assert result.returncode != 0


def test_run_tmux_when_nonzero(tmp_session_name):
    """`check=True` の非 0 終了を確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        ops._run_tmux(["kill-session", "-t", tmp_session_name])
