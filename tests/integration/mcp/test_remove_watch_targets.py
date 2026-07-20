"""「監視対象除去」の結合テスト。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

import server
from models import MonitorAck


def test_normal(tmp_settings, fake_remote, urlopen_calls):
    """MCP 委譲 → HTTP DELETE → 監視面除去の一連を確認する（正常系）。"""
    # 実行
    res = server.remove_watch_targets("architect", 52, [60, 61])
    # 検証
    req = urlopen_calls[0]
    assert req.full_url == "http://127.0.0.1:18999/watch-targets"
    assert req.get_method() == "DELETE"
    assert json.loads(req.data) == {
        "agent_name": "architect",
        "number": 52,
        "watch_numbers": [60, 61],
        "project": "shuhei1101/ai-monitor-e2e",
    }
    assert res == MonitorAck(ok=True)


def test_error_when_unknown_session(tmp_settings, fake_remote, monkeypatch):
    """台帳に該当セッションがない場合の 404 エラーを確認する（異常系・セッション不明・404）。"""
    # 準備
    def fake(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    # 実行・検証
    with pytest.raises(urllib.error.HTTPError):
        server.remove_watch_targets("architect", 52, [60])
