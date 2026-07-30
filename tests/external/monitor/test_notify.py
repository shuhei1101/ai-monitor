"""Webhook 送出の外部疎通テスト（実チャンネルへ投稿する）。"""
from __future__ import annotations

from ai_monitor.integrations.webhook.client import post_webhook

MESSAGE = "ai-monitor 外部疎通テスト（自動投稿）"


def test_ext_post_webhook_when_discord(discord_webhook_url):
    """Discord へ実投稿できることを確認する（正常系）。"""
    # 実行
    reason = post_webhook(discord_webhook_url, "discord", MESSAGE)
    # 検証
    assert reason == "", f"Discord への投稿に失敗した: {reason}"


def test_ext_post_webhook_when_slack(slack_webhook_url):
    """Slack へ実投稿できることを確認する（正常系）。"""
    # 実行
    reason = post_webhook(slack_webhook_url, "slack", MESSAGE)
    # 検証
    assert reason == "", f"Slack への投稿に失敗した: {reason}"