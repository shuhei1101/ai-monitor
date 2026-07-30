"""`src/ai_monitor/integrations/github/client.py` の疎通確認の単体テスト。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_monitor.integrations.github.client import check_github


@pytest.fixture
def gh_client(monkeypatch):
    """疎通確認が使う githubkit クライアントを MagicMock に差し替える。"""
    from ai_monitor.integrations.github import client as gh_client_mod

    mock = MagicMock(name="githubkit_client")
    monkeypatch.setattr(gh_client_mod, "_client", mock, raising=False)
    return mock


def test_check_github(gh_client, resp):
    """認証ユーザーを取得できたら空文字を返す（正常系）。"""
    # 準備
    gh_client.rest.users.get_authenticated.return_value = resp(MagicMock(login="shuhei1101"))
    # 実行
    reason = check_github()
    # 検証
    assert reason == ""
    assert gh_client.rest.users.get_authenticated.call_count == 1


def test_check_github_when_unauthorized(gh_client, request_failed):
    """トークン失効は応答コードを理由にする（正常系）。"""
    # 準備
    gh_client.rest.users.get_authenticated.side_effect = request_failed(401)
    # 実行
    reason = check_github()
    # 検証
    assert "401" in reason


def test_check_github_when_transport_error(gh_client):
    """通信に失敗しても例外を伝播させず理由を返す（正常系）。"""
    # 準備
    from githubkit.exception import RequestError

    gh_client.rest.users.get_authenticated.side_effect = RequestError("接続できない")
    # 実行
    reason = check_github()
    # 検証
    assert "RequestError" in reason
