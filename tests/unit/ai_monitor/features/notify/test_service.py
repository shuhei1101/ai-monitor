"""`src/ai_monitor/features/notify/service.py` の単体テスト。"""
from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from ai_monitor.features.notify.service import (
    build_message,
    build_notifier,
    build_targets,
    notify_event,
    send_notification,
)
from ai_monitor.features.notify.types import SendTarget
from ai_monitor.shared.settings import WebhookNotifySettings

REPO = "owner/name"
DISCORD_URL = "https://discord.com/api/webhooks/1234/abcd"
SLACK_URL = "https://hooks.slack.com/services/xxxx"


def _settings(**overrides) -> WebhookNotifySettings:
    """既定値つきの Webhook 通知設定を作る。"""
    values = {"webhook_url": SecretStr(DISCORD_URL), "kind": "discord"} | overrides
    return WebhookNotifySettings(**values)


@pytest.fixture
def target():
    """送出先のスタブを作る factory を返す（渡った本文を記録する）。"""

    def _make(name: str = "stub", reason: str = ""):
        calls: list[str] = []

        def _send(text):
            calls.append(text)
            return reason

        _send.calls = calls
        return SendTarget(name=name, send=_send)

    return _make


@pytest.fixture
def posted(monkeypatch):
    """httpx.post を差し替え、POST の引数を記録するリストを返す。"""
    records: list[dict] = []

    def _post(url, json=None, timeout=None):
        records.append({"url": url, "json": json})
        return httpx.Response(204, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _post)
    return records


def test_build_message():
    """番号を渡さない場合は対象へのリンクを付けない（正常系）。"""
    # 実行
    text = build_message("architect", "判断をお願いします", "候補が出揃いました")
    # 検証
    assert "architect" in text.splitlines()[0]
    assert "判断をお願いします" in text.splitlines()[0]
    assert "候補が出揃いました" in text
    assert "https://github.com/" not in text


def test_build_message_when_number():
    """番号とリポジトリが揃うと末尾に対象へのリンクを付ける（正常系）。"""
    # 実行
    text = build_message("architect", "見出し", "本文", repo=REPO, number=1069)
    # 検証
    assert text.endswith("https://github.com/owner/name/issues/1069")


def test_build_message_when_over_limit():
    """上限を超える本文は末尾を切って返す（正常系）。"""
    # 実行
    text = build_message("architect", "見出し", "あ" * 3000)
    # 検証
    assert len(text) <= 2000


def test_build_targets(posted):
    """複数の有効な設定から並び順どおりに送出先を作る（正常系）。"""
    # 準備
    settings_list = [
        _settings(),
        _settings(webhook_url=SecretStr(SLACK_URL), kind="slack"),
    ]
    # 実行
    targets = build_targets(settings_list)
    for t in targets:
        t.send("本文")
    # 検証
    assert [t.name for t in targets] == ["webhook:discord", "webhook:slack"]
    assert posted[0]["url"] == DISCORD_URL and posted[0]["json"] == {"content": "本文"}
    assert posted[1]["url"] == SLACK_URL and posted[1]["json"] == {"text": "本文"}


def test_build_targets_when_disabled():
    """enabled が False の設定は送出先に含めない（正常系）。"""
    # 準備
    settings_list = [
        _settings(enabled=False),
        _settings(webhook_url=SecretStr(SLACK_URL), kind="slack"),
    ]
    # 実行
    targets = build_targets(settings_list)
    # 検証
    assert [t.name for t in targets] == ["webhook:slack"]


def test_build_targets_when_named():
    """識別名は設定値を優先し、未設定なら方式と種別から作る（正常系）。"""
    # 準備
    settings_list = [
        _settings(name="社内 Slack"),
        _settings(webhook_url=SecretStr(SLACK_URL), kind="slack"),
    ]
    # 実行
    targets = build_targets(settings_list)
    # 検証
    assert [t.name for t in targets] == ["社内 Slack", "webhook:slack"]


def test_send_notification(target):
    """全送出先へ同じ本文を送り、並び順どおりに結果を返す（正常系）。"""
    # 準備
    first, second = target("discord"), target("slack")
    # 実行
    result = send_notification(
        "architect", "見出し", "本文", targets=[first, second], repo=REPO, number=1069
    )
    # 検証
    assert result.sent is True
    assert [r.target for r in result.results] == ["discord", "slack"]
    assert all(r.sent for r in result.results)
    assert first.send.calls == second.send.calls
    assert "architect" in first.send.calls[0]
    assert "1069" in first.send.calls[0]


def test_send_notification_when_no_targets():
    """送出先が 0 件なら送らずに空の結果を返す（正常系）。"""
    # 実行
    result = send_notification("architect", "見出し", "本文", targets=[])
    # 検証
    assert result.sent is False
    assert result.results == []


def test_send_notification_when_partially_fails(target):
    """1 件目が失敗しても後続へ送り続ける（正常系）。"""
    # 準備
    first = target("discord", reason="ConnectError: 接続できない")
    second = target("slack")
    # 実行
    result = send_notification("architect", "見出し", "本文", targets=[first, second])
    # 検証
    assert result.sent is True
    assert result.results[0].sent is False
    assert "ConnectError" in result.results[0].reason
    assert result.results[1].sent is True
    assert second.send.calls


def test_send_notification_when_all_fail(target):
    """全て失敗したら送信先ごとの理由を添えて全体を失敗にする（正常系）。"""
    # 準備
    first = target("discord", reason="429 Too Many Requests")
    second = target("slack", reason="404 Not Found")
    # 実行
    result = send_notification("architect", "見出し", "本文", targets=[first, second])
    # 検証
    assert result.sent is False
    assert [r.reason for r in result.results] == ["429 Too Many Requests", "404 Not Found"]


def test_notify_event(target):
    """契機が有効な全送出先へ monitor 名義で送る（正常系）。"""
    # 準備
    settings_list = [_settings(), _settings(kind="slack")]
    targets = [target("discord"), target("slack")]
    # 実行
    result = notify_event("rate_limit", "見出し", "本文", settings_list, targets=targets)
    # 検証
    assert result.sent is True
    assert len(result.results) == 2
    assert "monitor" in targets[0].send.calls[0]


def test_notify_event_when_partially_disabled(target):
    """契機を無効にした送出先へは送らない（正常系）。"""
    # 準備
    settings_list = [_settings(events={"rate_limit": False}), _settings(kind="slack")]
    targets = [target("discord"), target("slack")]
    # 実行
    result = notify_event("rate_limit", "見出し", "本文", settings_list, targets=targets)
    # 検証
    assert [r.target for r in result.results] == ["slack"]
    assert not targets[0].send.calls
    assert targets[1].send.calls


def test_notify_event_when_all_disabled(target):
    """全送出先で契機が無効なら送らない（正常系）。"""
    # 準備
    settings_list = [_settings(events={"rate_limit": False})]
    targets = [target("discord")]
    # 実行
    result = notify_event("rate_limit", "見出し", "本文", settings_list, targets=targets)
    # 検証
    assert result.sent is False
    assert result.results == []
    assert not targets[0].send.calls


def test_notify_event_when_event_not_listed(target):
    """events に記載の無い契機は送る扱いにする（正常系）。"""
    # 準備: 別の契機だけを無効にしている設定
    settings_list = [_settings(events={"epic_done": False})]
    targets = [target("discord")]
    # 実行
    result = notify_event("rate_limit", "見出し", "本文", settings_list, targets=targets)
    # 検証
    assert result.sent is True
    assert targets[0].send.calls


def test_build_notifier(posted):
    """設定から送出先を組み立てた通知関数を返す（正常系）。"""
    # 準備
    settings_list = [_settings()]
    # 実行
    notify = build_notifier(settings_list)
    result = notify("rate_limit", "見出し", "本文")
    # 検証
    assert result.sent is True
    assert posted[0]["url"] == DISCORD_URL


def test_build_notifier_when_empty(posted):
    """設定が空なら呼んでも送らない関数を返す（正常系）。"""
    # 実行
    notify = build_notifier([])
    result = notify("rate_limit", "見出し", "本文")
    # 検証
    assert result.sent is False
    assert not posted
