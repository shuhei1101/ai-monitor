"""「子Issue作成」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import CreatedIssueResult


def test_normal(gh, resp):
    """Issue 作成 → REST id 取得 → Sub-issue リンク付与の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create.return_value = resp(NS(number=36, id=999, html_url="http://i/36"))
    # 実行
    res = server.create_child_issue(35, title="子", body="本文", labels=["layer:story"])
    # 検証
    assert gh.rest.issues.add_sub_issue.call_args.kwargs["sub_issue_id"] == 999
    assert res == CreatedIssueResult(issue_number=36, url="http://i/36", parent_issue_number=35)


def test_error_when_link_fails(gh, resp, request_failed):
    """リンク付与失敗時に子 Issue は作成済みのままエラーが伝播することを確認する（異常系）。"""
    # 準備
    gh.rest.issues.create.return_value = resp(NS(number=36, id=999, html_url="http://i/36"))
    gh.rest.issues.add_sub_issue.side_effect = request_failed(422)
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.create_child_issue(35, title="子", body="本文")
    gh.rest.issues.create.assert_called_once()
