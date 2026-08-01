"""「レビュースレッド返信」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import GraphQLFailed


def _reply_payload(node_id="PRRC_9", url="http://r/9"):
    return {"addPullRequestReviewThreadReply": {"comment": {"id": node_id, "url": url}}}


def test_normal(gh, api):
    """ヘッダー組み立て → スレッドへの返信投稿の一連を確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = _reply_payload()
    # 実行
    res = api.reply_review_thread(
        "PRRT_1", sender="implementer", receiver="architect", body="commit abc1234 で修正しました。"
    )
    # 検証
    query, variables = gh.graphql.call_args.args
    assert "addPullRequestReviewThreadReply" in query
    assert variables["id"] == "PRRT_1"
    assert variables["body"].startswith("> from: @implementer\n> to: @architect")
    assert "commit abc1234 で修正しました。" in variables["body"]
    # 1 返信 = 1 コメントなので末尾に区切り線を付けない
    assert not variables["body"].endswith("---\n")
    assert (res.node_id, res.url) == ("PRRC_9", "http://r/9")


def test_error_when_api_error(gh, graphql_failed, api):
    """スレッド不存在等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.graphql.side_effect = graphql_failed()
    # 実行・検証
    with pytest.raises(GraphQLFailed):
        api.reply_review_thread("PRRT_999", sender="implementer", body="対応しました。")
