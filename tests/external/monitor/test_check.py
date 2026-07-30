"""起動時の依存確認の外部疎通テスト（実 API 実測）。"""
from __future__ import annotations

from ai_monitor.integrations.github.client import check_github
from ai_monitor.integrations.webhook.client import check_webhook


def test_ext_check_github(gh_live):
    """PAT で認証ユーザーを取得できることを確認する（正常系）。"""
    # 実行
    reason = check_github()
    # 検証
    assert reason == "", f"GitHub API へ疎通できていない: {reason}"


def test_ext_check_webhook_when_discord(discord_webhook_url):
    """Discord Webhook の URL へ到達できることを確認する（正常系）。"""
    # 実行
    reason = check_webhook(discord_webhook_url)
    # 検証
    assert reason == "", f"Discord Webhook へ到達できていない: {reason}"