"""「assignee設定」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import AssigneesResult


def test_normal(gh, resp):
    """認証ユーザー解決 → 設定 → 現況再取得の一連を確認する（正常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.get.return_value = resp(NS(assignees=[NS(login="shuhei1101")]))
    # 実行
    res = server.set_assignee(35, is_pr=False)
    # 検証
    assert gh.rest.issues.add_assignees.call_args.kwargs["assignees"] == ["shuhei1101"]
    assert res == AssigneesResult(assignees=["shuhei1101"])


def test_normal_when_already_assigned(gh, resp):
    """設定済みの再設定が no-op で現況を返すことを確認する（正常系・設定済み時）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.get.return_value = resp(NS(assignees=[NS(login="shuhei1101")]))
    # 実行
    res = server.set_assignee(35, is_pr=False)
    # 検証
    assert res == AssigneesResult(assignees=["shuhei1101"])


def test_error_when_api_error(gh, resp, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = resp(NS(login="shuhei1101"))
    gh.rest.issues.add_assignees.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.set_assignee(35, is_pr=False)
