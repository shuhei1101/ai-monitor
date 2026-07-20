"""「コメント返信」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import GraphQLFailed

import server


def test_normal(gh, resp):
    """既存本文取得 → 定型ブロック追記 → 本文更新の一連を確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = {"node": {"body": "元コメント", "databaseId": 111}}
    gh.rest.issues.update_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    # 実行
    res = server.reply_comment("IC_1", sender="tester", body="修正しました。")
    # 検証
    kwargs = gh.rest.issues.update_comment.call_args.kwargs
    assert kwargs["comment_id"] == 111
    assert kwargs["body"] == "元コメント\n\n---\n> from: @tester\n\n修正しました。"
    assert res.node_id == "IC_1"


def test_error_when_api_error(gh, graphql_failed):
    """node_id 不正等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.graphql.side_effect = graphql_failed()
    # 実行・検証
    with pytest.raises(GraphQLFailed):
        server.reply_comment("IC_bad", sender="tester", body="本文")
