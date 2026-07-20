"""「宛先コメント一覧」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server


def _comment_ns(node_id, body):
    return NS(node_id=node_id, body=body, user=NS(login="shuhei1101"), html_url=f"http://c/{node_id}")


def test_normal(gh, resp):
    """取得 → Resolved 除外 → ブロックパース → 宛先判定の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.list_comments.return_value = resp(
        [
            _comment_ns("IC_1", "> from: @tester\n> to: @architect\n\n完了しました。"),
            _comment_ns("IC_2", "> from: @tester\n> to: @architect\n\nResolved 済みの報告。"),
            _comment_ns("IC_3", "> from: @architect\n> to: @tester\n\n宛先違い。"),
            _comment_ns("IC_4", "素のユーザーコメント。"),
        ]
    )
    gh.graphql.side_effect = [
        {"node": {"isMinimized": False}},
        {"node": {"isMinimized": True}},
        {"node": {"isMinimized": False}},
        {"node": {"isMinimized": False}},
    ]
    # 実行
    res = server.list_addressed_comments(52, is_pr=True, addressee="architect")
    # 検証
    assert [c.node_id for c in res] == ["IC_1", "IC_4"]
    assert res[0].blocks[-1].sender == "tester"
    assert res[1].blocks[-1].sender is None


def test_error_when_api_error(gh, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.list_comments.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.list_addressed_comments(52, is_pr=True, addressee="architect")
