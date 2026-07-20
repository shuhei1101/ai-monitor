"""「PR_Ready化」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import EmptyResult


def test_normal(gh, resp):
    """node_id 取得 → markPullRequestReadyForReview mutation の一連を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = resp(NS(node_id="PR_1", head=NS(ref="feat/x", sha="S")))
    # 実行
    res = server.mark_pr_ready(52)
    # 検証
    query, variables = gh.graphql.call_args.args
    assert "markPullRequestReadyForReview" in query
    assert variables == {"id": "PR_1"}
    assert res == EmptyResult()


def test_error_when_api_error(gh, request_failed):
    """対象不存在等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.pulls.get.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.mark_pr_ready(999)
