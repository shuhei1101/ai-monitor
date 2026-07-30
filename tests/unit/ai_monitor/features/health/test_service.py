"""`src/ai_monitor/features/health/service.py` の単体テスト。"""
from __future__ import annotations

import pytest
from pydantic import SecretStr

from ai_monitor.features.health.service import check_dependencies
from ai_monitor.shared.settings import WebhookNotifySettings

DISCORD_URL = "https://discord.com/api/webhooks/1234/abcd"
SLACK_URL = "https://hooks.slack.com/services/xxxx"


def _settings(**overrides) -> WebhookNotifySettings:
    """既定値つきの Webhook 通知設定を作る。"""
    values = {"webhook_url": SecretStr(DISCORD_URL), "kind": "discord"} | overrides
    return WebhookNotifySettings(**values)


@pytest.fixture
def checker():
    """疎通確認のスタブを作る factory を返す（呼び出しを記録する）。"""

    def _make(reason: str = ""):
        calls: list = []

        def _check(*args):
            calls.append(args)
            return reason

        _check.calls = calls
        return _check

    return _make


def test_check_dependencies(checker):
    """全依存に繋がったら依存ごとの結果を順に返す（正常系）。"""
    # 準備
    github, webhook = checker(), checker()
    settings_list = [_settings(), _settings(name="社内 Slack", kind="slack")]
    # 実行
    results = check_dependencies(
        settings_list, check_github_fn=github, check_webhook_fn=webhook
    )
    # 検証
    assert [r.name for r in results] == ["GitHub API", "webhook:discord", "社内 Slack"]
    assert all(r.ok for r in results)
    assert results[0].required is True
    assert all(r.required is False for r in results[1:])
    assert len(webhook.calls) == 2


def test_check_dependencies_when_github_fails(checker):
    """必須依存が失敗したらそこで打ち切る（正常系）。"""
    # 準備
    github, webhook = checker("401 Unauthorized"), checker()
    # 実行
    results = check_dependencies(
        [_settings()], check_github_fn=github, check_webhook_fn=webhook
    )
    # 検証
    assert len(results) == 1
    assert results[0].required is True and results[0].ok is False
    assert "401" in results[0].reason
    assert not webhook.calls


def test_check_dependencies_when_webhook_fails(checker):
    """補助依存が失敗しても後続の送信先を確認し続ける（正常系）。"""
    # 準備: 1 件目だけ失敗させる
    calls: list = []

    def _webhook(url):
        calls.append(url)
        return "ConnectError: 接続できない" if url == DISCORD_URL else ""

    settings_list = [_settings(), _settings(webhook_url=SecretStr(SLACK_URL), kind="slack")]
    # 実行
    results = check_dependencies(
        settings_list, check_github_fn=checker(), check_webhook_fn=_webhook
    )
    # 検証
    assert len(results) == 3
    assert results[1].ok is False and "ConnectError" in results[1].reason
    assert results[2].ok is True
    assert calls == [DISCORD_URL, SLACK_URL]


def test_check_dependencies_when_disabled(checker):
    """無効にした送信先は確認しない（正常系）。"""
    # 準備
    github, webhook = checker(), checker()
    settings_list = [_settings(enabled=False), _settings(kind="slack")]
    # 実行
    results = check_dependencies(
        settings_list, check_github_fn=github, check_webhook_fn=webhook
    )
    # 検証
    assert [r.name for r in results] == ["GitHub API", "webhook:slack"]
    assert len(webhook.calls) == 1


def test_check_dependencies_when_no_notifies(checker):
    """送信先が無ければ GitHub の結果だけを返す（正常系）。"""
    # 準備
    github, webhook = checker(), checker()
    # 実行
    results = check_dependencies([], check_github_fn=github, check_webhook_fn=webhook)
    # 検証
    assert [r.name for r in results] == ["GitHub API"]
    assert not webhook.calls
