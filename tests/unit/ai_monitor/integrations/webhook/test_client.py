"""`src/ai_monitor/integrations/webhook/client.py` の単体テスト。"""
from __future__ import annotations

import httpx
import pytest

from ai_monitor.integrations.webhook.client import build_payload, post_webhook

WEBHOOK_URL = "https://discord.com/api/webhooks/1234/abcd"
TEXT = "> from: @architect\n判断をお願いします"


@pytest.fixture
def responses():
    """POST に渡った引数を記録するスタブを返す。"""
    calls: list[dict] = []

    def _make(status_code: int | None = 204, *, error: Exception | None = None):
        def _post(url, json=None, timeout=None):
            calls.append({"url": url, "json": json, "timeout": timeout})
            if error is not None:
                raise error
            return httpx.Response(status_code, request=httpx.Request("POST", url))

        _post.calls = calls
        return _post

    return _make


def test_build_payload_when_discord():
    """Discord のペイロードは content キーで組み立てる（正常系）。"""
    # 実行
    payload = build_payload("discord", TEXT)
    # 検証
    assert payload == {"content": TEXT}


def test_build_payload_when_slack():
    """Slack のペイロードは text キーで組み立てる（正常系）。"""
    # 実行
    payload = build_payload("slack", TEXT)
    # 検証
    assert payload == {"text": TEXT}


def test_post_webhook(monkeypatch, responses):
    """2xx 応答なら空文字を返し POST は 1 回だけ行う（正常系）。"""
    # 準備
    post = responses(204)
    monkeypatch.setattr(httpx, "post", post)
    # 実行
    reason = post_webhook(WEBHOOK_URL, "discord", TEXT)
    # 検証
    assert reason == ""
    assert len(post.calls) == 1
    assert post.calls[0]["url"] == WEBHOOK_URL
    assert post.calls[0]["json"] == {"content": TEXT}


def test_post_webhook_when_error_status(monkeypatch, responses):
    """2xx 以外なら応答コードを理由にして再送しない（正常系）。"""
    # 準備
    post = responses(429)
    monkeypatch.setattr(httpx, "post", post)
    # 実行
    reason = post_webhook(WEBHOOK_URL, "discord", TEXT)
    # 検証
    assert "429" in reason
    assert len(post.calls) == 1


def test_post_webhook_when_transport_error(monkeypatch, responses):
    """通信に失敗しても例外を伝播させず理由を返す（正常系）。"""
    # 準備
    post = responses(error=httpx.ConnectError("接続できない"))
    monkeypatch.setattr(httpx, "post", post)
    # 実行
    reason = post_webhook(WEBHOOK_URL, "slack", TEXT)
    # 検証
    assert reason
    assert "ConnectError" in reason
