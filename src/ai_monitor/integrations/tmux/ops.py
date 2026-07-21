"""tmux セッションの実体操作。"""
from __future__ import annotations

import subprocess
import time


def create_session(name: str, cwd: str) -> None:
    """tmux セッションを detached で作成する。"""
    _run_tmux(["new-session", "-d", "-s", name, "-c", cwd])


def send_keys(name: str, text: str) -> None:
    """既存セッションへ文字列を送信して実行させる。"""
    # テキストと Enter を同時に送ると貼り付け判定で改行が入力扱いになるため、間を置いて別送する
    _run_tmux(["send-keys", "-t", name, text])
    time.sleep(1)
    _run_tmux(["send-keys", "-t", name, "Enter"])


def has_session(name: str) -> bool:
    """セッションの存在を確認する。"""
    result = _run_tmux(["has-session", "-t", name], check=False)
    return result.returncode == 0


def kill_session(name: str) -> None:
    """セッションを kill する。"""
    _run_tmux(["kill-session", "-t", name])


def _run_tmux(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """tmux CLI 呼び出しの単一入口。"""
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=check)
