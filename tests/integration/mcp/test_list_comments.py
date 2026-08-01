"""「コメント一覧」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed



def _comment_ns(node_id, body):
    return NS(node_id=node_id, body=body, user=NS(login="shuhei1101"), html_url=f"http://c/{node_id}")


def test_normal(gh, resp, api):
    """取得 → Resolved 除外 → ブロックパース → 宛先判定の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.list_comments.return_value = resp(
        [
            _comment_ns("IC_1", "> from: @tester\n> to: @architect\n\n完了しました。"),
            _comment_ns("IC_2", "> from: @tester\n> to: @architect\n\nResolved 済みの報告。"),
            _comment_ns("IC_3", "> from: @tester\n> to: @implementer\n\n宛先違い。"),
            _comment_ns("IC_4", "素のユーザーコメント。"),
            _comment_ns("IC_5", "> from: @architect\n> to: @shuhei1101\n\n自身の投稿。"),
        ]
    )
    gh.graphql.side_effect = [
        {"node": {"isMinimized": False}},
        {"node": {"isMinimized": True}},
        {"node": {"isMinimized": False}},
        {"node": {"isMinimized": False}},
        {"node": {"isMinimized": False}},
    ]
    # 実行
    res = api.list_comments(52, is_pr=True, addressee="architect")
    # 検証
    # Resolved 済み（IC_2）だけが落ち、宛先違い（IC_3）も is_addressed=False で返る
    assert [c.node_id for c in res] == ["IC_1", "IC_3", "IC_4", "IC_5"]
    assert [c.is_addressed for c in res] == [True, False, True, True]
    assert res[0].blocks[-1].sender == "tester"
    assert res[2].blocks[-1].sender is None
    assert res[3].blocks[-1].sender == "architect"


def test_normal_when_user_appended(gh, resp, api):
    """末尾の区切り線の有無でブロック数が変わらないことを確認する（正常系）。"""
    # 準備
    agent_block = "> from: @architect\n> to: @shuhei1101\n\n設計を更新しました。\n\n---\n"
    gh.rest.issues.list_comments.return_value = resp(
        [
            # ユーザーが区切り線を置かずに書き足したコメント
            _comment_ns("IC_1", f"{agent_block}\n\nこの観点も追加してほしい。"),
            # ユーザーが書き足しの後にも区切り線を置いたコメント
            _comment_ns("IC_2", f"{agent_block}\n\nこの観点も追加してほしい。\n\n---\n"),
        ]
    )
    gh.graphql.side_effect = [{"node": {"isMinimized": False}}, {"node": {"isMinimized": False}}]
    # 実行
    res = api.list_comments(52, is_pr=True, addressee="architect")
    # 検証
    assert [c.node_id for c in res] == ["IC_1", "IC_2"]
    # 末尾の区切り線の有無で件数が変わらず、空のブロックも含まれない
    assert [len(c.blocks) for c in res] == [2, 2]
    for comment in res:
        assert all(block.body for block in comment.blocks)
        # 最終ブロックは from なし（ユーザー投稿）= 現担当宛と判定される
        assert comment.blocks[-1].sender is None
        assert comment.blocks[-1].receiver is None
        assert comment.is_addressed is True


def test_error_when_api_error(gh, request_failed, api):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.list_comments.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.list_comments(52, is_pr=True, addressee="architect")
