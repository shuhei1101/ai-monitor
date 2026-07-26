"""`plugins/ai-monitor/hooks/pre-compact/request_context_reset.py` の単体テスト。"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

HOOK_DIR = Path(__file__).resolve().parents[3] / "plugins" / "ai-monitor" / "hooks" / "pre-compact"
sys.path.insert(0, str(HOOK_DIR))

import request_context_reset  # noqa: E402


@pytest.fixture
def hook_env(monkeypatch):
    """モニターが tmux 起動時に渡す 4 変数を与える。"""
    monkeypatch.setenv("AI_MONITOR_PROJECT", "sandbox")
    monkeypatch.setenv("AI_MONITOR_AGENT", "subsystem-conductor")
    monkeypatch.setenv("AI_MONITOR_NUMBER", "170")
    monkeypatch.setenv("AI_MONITOR_PORT", "8765")


def test_main(hook_env, urlopen_calls, capsys):
    """要求の送信とブロックを確認する（正常系）。"""
    # 実行
    code = request_context_reset.main()
    # 検証: 指定 URL へ素性を含む POST が 1 回
    assert code == 0
    assert len(urlopen_calls) == 1
    request = urlopen_calls[0]
    assert request.full_url == "http://127.0.0.1:8765/context_reset"
    assert request.method == "POST"
    assert json.loads(request.data) == {
        "project": "sandbox",
        "agent_name": "subsystem-conductor",
        "number": 170,
    }
    # 検証: コンパクトをブロックする指示を標準出力に書く
    assert json.loads(capsys.readouterr().out)["decision"] == "block"


def test_main_when_env_missing(hook_env, urlopen_calls, monkeypatch, capsys):
    """環境変数の欠落を確認する（正常系）。"""
    # 準備: モニター起動でないセッションを再現する
    monkeypatch.delenv("AI_MONITOR_AGENT")
    # 実行
    code = request_context_reset.main()
    # 検証: POST もブロック指示も発生しない（コンパクトを通常どおり行わせる）
    assert code == 0
    assert urlopen_calls == []
    assert capsys.readouterr().out == ""


def test_main_when_request_fails(hook_env, monkeypatch, capsys):
    """通信失敗を確認する（正常系）。"""
    # 準備: モニターが起動していない状態を再現する
    def fail(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    # 実行
    code = request_context_reset.main()
    # 検証: 例外が伝播せず、ブロックもしない（リセットが届かないならコンパクトを止めない）
    assert code == 0
    assert capsys.readouterr().out == ""
