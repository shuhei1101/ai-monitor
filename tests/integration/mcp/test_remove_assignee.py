"""「assignee除去」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import AssigneesResult


def test_normal(gh, resp):
    """認証ユーザー解決 → 除去 → 現況再取得の一連を確認する（正常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.get.return_value = resp(NS(assignees=[]))
    # 実行
    res = server.remove_assignee(35, is_pr=False)
    # 検証
    assert gh.rest.issues.remove_assignees.call_args.kwargs["assignees"] == ["shuhei1101"]
    assert res == AssigneesResult(assignees=[])


def test_normal_when_not_assigned(gh, resp):
    """未設定の除去が no-op で現況を返すことを確認する（正常系・対象が未設定時）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.get.return_value = resp(NS(assignees=[]))
    # 実行
    res = server.remove_assignee(35, is_pr=False)
    # 検証
    assert res == AssigneesResult(assignees=[])


def test_error_when_api_error(gh, resp, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.remove_assignees.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.remove_assignee(35, is_pr=False)
