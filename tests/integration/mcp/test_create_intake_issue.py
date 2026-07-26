"""「新規Issue起票」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import CreatedIssueResult


def test_normal(gh, resp, api):
    """Issue 作成 → 固定ラベル付与 → 番号と URL の返却の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create.return_value = resp(NS(number=58, id=1001, html_url="http://i/58"))
    # 実行
    res = api.create_intake_issue(title="並び替えを追加したい", body="#42 の会話から派生。")
    # 検証: 固定ラベルで作成され、親リンクは作られない
    assert gh.rest.issues.create.call_args.kwargs["labels"] == [
        "layer:intake",
        "確認:intake-issue-triager",
    ]
    gh.rest.issues.add_sub_issue.assert_not_called()
    assert res == CreatedIssueResult(issue_number=58, url="http://i/58", parent_issue_number=None)


def test_error_when_api_error(gh, request_failed, api):
    """作成失敗がツールエラーとして伝播することを確認する（異常系）。"""
    # 準備
    gh.rest.issues.create.side_effect = request_failed(422)
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.create_intake_issue(title="並び替えを追加したい", body="本文")
