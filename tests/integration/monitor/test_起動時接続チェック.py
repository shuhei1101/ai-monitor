"""「起動時接続チェック」の結合テスト。"""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import SecretStr

import ai_monitor.main as main_mod
from ai_monitor.shared.settings import WebhookNotifySettings

DISCORD_URL = "https://discord.com/api/webhooks/1234/abcd"
SLACK_URL = "https://hooks.slack.com/services/xxxx"


@pytest.fixture
def boot(monkeypatch, mon_settings, label_settings, agent_settings, tmp_state_path):
    """main() を実行する準備を整え、起動したかを返す factory を返す。"""
    mon_settings.agents = agent_settings
    mon_settings.state_path = str(tmp_state_path)
    mon_settings.github_token = SecretStr("github_pat_test")
    started: list[bool] = []

    monkeypatch.setattr(main_mod, "Settings", lambda: mon_settings)
    monkeypatch.setattr(main_mod, "LabelSettings", lambda: label_settings)
    monkeypatch.setattr(main_mod, "get_client", lambda settings: MagicMock())
    monkeypatch.setattr(main_mod, "configure", lambda name: None)
    monkeypatch.setattr(main_mod, "create_app", lambda *a, **k: MagicMock())
    # 監視役の起動は本テストの対象外なので差し替える（実プロセスを立てない）
    monkeypatch.setattr(main_mod, "ensure_watchdog_started", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "build_settings_reader", lambda read: read)
    monkeypatch.setattr(main_mod, "build_notifier", lambda read: (lambda *a, **k: None))
    # uvicorn の起動をフックして「起動したか」を観測する
    monkeypatch.setattr(
        main_mod.uvicorn, "run", lambda app, host=None, port=None: started.append(True)
    )

    def _run() -> tuple[int, bool]:
        code = main_mod.main()
        return code, bool(started)

    return _run


@pytest.fixture
def github_ok(monkeypatch):
    """GitHub の疎通確認を成功に差し替える。"""
    monkeypatch.setattr(main_mod, "check_github", lambda: "")


@pytest.fixture
def webhook_calls(monkeypatch):
    """Webhook の疎通確認を差し替え、確認した URL を記録するリストを返す。"""
    calls: list[str] = []
    failing: dict[str, str] = {}

    def _check(url):
        calls.append(url)
        return failing.get(url, "")

    monkeypatch.setattr(main_mod, "check_webhook", _check)
    _check.failing = failing
    return calls, failing


def test_normal(boot, github_ok, webhook_calls, mon_settings):
    """全依存に繋がれば起動することを確認する（正常系）。"""
    # 準備
    calls, _ = webhook_calls
    mon_settings.notifies = [
        WebhookNotifySettings(webhook_url=SecretStr(DISCORD_URL), kind="discord")
    ]
    # 実行
    code, started = boot()
    # 検証
    assert code == 0
    assert started is True
    assert calls == [DISCORD_URL]


def test_normal_when_webhook_unreachable(boot, github_ok, webhook_calls, mon_settings):
    """送信先が繋がらなくても起動を続けることを確認する（正常系）。"""
    # 準備: 1 件目だけ失敗させる
    calls, failing = webhook_calls
    failing[DISCORD_URL] = "ConnectError: 接続できない"
    mon_settings.notifies = [
        WebhookNotifySettings(webhook_url=SecretStr(DISCORD_URL), kind="discord"),
        WebhookNotifySettings(webhook_url=SecretStr(SLACK_URL), kind="slack"),
    ]
    # 実行
    code, started = boot()
    # 検証
    assert code == 0
    assert started is True
    assert calls == [DISCORD_URL, SLACK_URL]


def test_normal_when_no_notifies(boot, github_ok, webhook_calls, mon_settings):
    """送信先が未設定なら疎通確認を行わずに起動することを確認する（正常系）。"""
    # 準備
    calls, _ = webhook_calls
    mon_settings.notifies = []
    # 実行
    code, started = boot()
    # 検証
    assert code == 0
    assert started is True
    assert not calls


def test_error_when_github_unreachable(boot, monkeypatch, webhook_calls, mon_settings):
    """GitHub API が繋がらなければ起動を中止することを確認する（異常系）。"""
    # 準備
    calls, _ = webhook_calls
    monkeypatch.setattr(main_mod, "check_github", lambda: "401")
    mon_settings.notifies = [
        WebhookNotifySettings(webhook_url=SecretStr(DISCORD_URL), kind="discord")
    ]
    # 実行
    code, started = boot()
    # 検証
    assert code == 1
    assert started is False
    assert not calls


def test_normal_when_target_disabled(boot, github_ok, webhook_calls, mon_settings):
    """無効にした送信先は疎通確認の対象外であることを確認する（正常系）。"""
    # 準備
    calls, _ = webhook_calls
    mon_settings.notifies = [
        WebhookNotifySettings(enabled=False, webhook_url=SecretStr(DISCORD_URL), kind="discord"),
        WebhookNotifySettings(webhook_url=SecretStr(SLACK_URL), kind="slack"),
    ]
    # 実行
    code, started = boot()
    # 検証
    assert code == 0
    assert calls == [SLACK_URL]
    assert httpx is not None
