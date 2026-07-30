"""「通知送出」の結合テスト。"""
from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from ai_monitor.shared.settings import WebhookNotifySettings

DISCORD_URL = "https://discord.com/api/webhooks/1234/abcd"
SLACK_URL = "https://hooks.slack.com/services/xxxx"


class _Posted(list):
    """POST の記録に、URL ごとの応答指定を持たせたリスト。"""

    def __init__(self):
        super().__init__()
        self.behavior: dict[str, object] = {}


@pytest.fixture
def posted(monkeypatch):
    """httpx.post を差し替え、POST の引数を記録するリストを返す。

    `behavior` に URL をキーで指定すると、その送信先だけ応答を差し替えられる。
    """
    records = _Posted()

    def _post(url, json=None, timeout=None):
        records.append({"url": url, "json": json})
        configured = records.behavior.get(url, 204)
        # 例外を指定した送信先は送信時に落とす（接続エラーの再現）
        if isinstance(configured, Exception):
            raise configured
        return httpx.Response(configured, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _post)
    return records


@pytest.fixture
def with_targets(mon_settings):
    """Discord と Slack の送信先を登録した全体設定を返す。"""
    mon_settings.notifies = [
        WebhookNotifySettings(webhook_url=SecretStr(DISCORD_URL), kind="discord"),
        WebhookNotifySettings(
            name="社内 Slack", webhook_url=SecretStr(SLACK_URL), kind="slack"
        ),
    ]
    return mon_settings


def test_normal(api, posted, with_targets):
    """有効な全送信先へ同じ本文を送ることを確認する（正常系）。"""
    # 実行
    res = api.notify(
        sender="architect", title="判断をお願いします", body="候補 3 件の PoC が成立しました", number=1069
    )
    # 検証
    assert res.sent is True
    assert [r.target for r in res.results] == ["webhook:discord", "社内 Slack"]
    assert all(r.sent and not r.reason for r in res.results)
    assert [p["url"] for p in posted] == [DISCORD_URL, SLACK_URL]
    assert posted[0]["json"].keys() == {"content"}
    assert posted[1]["json"].keys() == {"text"}
    text = posted[0]["json"]["content"]
    assert "architect" in text and "判断をお願いします" in text and "1069" in text


def test_normal_when_no_enabled_targets(api, posted, mon_settings):
    """有効な送信先が無ければ送らないことを確認する（正常系）。"""
    # 準備: 登録済みだが全て無効
    mon_settings.notifies = [
        WebhookNotifySettings(enabled=False, webhook_url=SecretStr(DISCORD_URL), kind="discord")
    ]
    # 実行
    res = api.notify(sender="architect", title="見出し", body="本文")
    # 検証
    assert res.sent is False
    assert res.results == []
    assert not posted


def test_error_when_partially_fails(api, posted, with_targets):
    """一部が失敗しても後続へ送り、送信先ごとの理由を返すことを確認する（異常系）。"""
    # 準備: 1 件目だけ接続エラーにする
    posted.behavior[DISCORD_URL] = httpx.ConnectError("接続できない")
    # 実行
    res = api.notify(sender="architect", title="見出し", body="本文")
    # 検証
    assert res.sent is True
    assert res.results[0].sent is False and "ConnectError" in res.results[0].reason
    assert res.results[1].sent is True and res.results[1].reason == ""
    assert [p["url"] for p in posted] == [DISCORD_URL, SLACK_URL]
