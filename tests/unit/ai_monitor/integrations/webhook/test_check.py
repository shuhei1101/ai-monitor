"""`src/ai_monitor/integrations/webhook/client.py` の疎通確認の単体テスト。"""
from __future__ import annotations

import httpx
import pytest

from ai_monitor.integrations.webhook.client import check_webhook

WEBHOOK_URL = "https://discord.com/api/webhooks/1234/abcd"


@pytest.fixture
def requested(monkeypatch):
    """httpx.get を差し替え、リクエストを記録するリストを返す。"""
    records: list[dict] = []
    behavior: dict[str, object] = {"status": 200}

    def _get(url, timeout=None):
        records.append({"url": url})
        configured = behavior["status"]
        if isinstance(configured, Exception):
            raise configured
        return httpx.Response(configured, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", _get)
    return records, behavior


def test_check_webhook(requested):
    """到達できたら空文字を返し、本文を送らない（正常系）。"""
    # 準備
    records, _ = requested
    # 実行
    reason = check_webhook(WEBHOOK_URL)
    # 検証
    assert reason == ""
    assert records == [{"url": WEBHOOK_URL}]


def test_check_webhook_when_not_found(requested):
    """URL 誤りは応答コードを理由にする（正常系）。"""
    # 準備
    _, behavior = requested
    behavior["status"] = 404
    # 実行
    reason = check_webhook(WEBHOOK_URL)
    # 検証
    assert "404" in reason


def test_check_webhook_when_transport_error(requested):
    """通信に失敗しても例外を伝播させず理由を返す（正常系）。"""
    # 準備
    _, behavior = requested
    behavior["status"] = httpx.ConnectError("接続できない")
    # 実行
    reason = check_webhook(WEBHOOK_URL)
    # 検証
    assert "ConnectError" in reason
