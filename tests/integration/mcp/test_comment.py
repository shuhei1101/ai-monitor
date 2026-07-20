"""「コメント投稿」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import CommentResult


def test_normal(gh, resp):
    """定型ブロック組み立て → REST 投稿の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    # 実行
    res = server.comment(35, is_pr=False, sender="architect", receiver="shuhei1101", body="設計を更新しました。")
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert posted.startswith("> from: @architect\n> to: @shuhei1101")
    assert res == CommentResult(node_id="IC_1", url="http://c/1")


def test_error_when_api_error(gh, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.create_comment.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.comment(35, is_pr=False, sender="architect", body="本文")
