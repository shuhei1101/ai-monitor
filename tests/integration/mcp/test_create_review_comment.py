"""「インラインコメント投稿」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server


def test_normal(gh, resp):
    """定型ブロック組み立て → head SHA 取得 → レビューコメント投稿の一連を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = resp(NS(head=NS(sha="SHA1", ref="feat/x"), node_id="PR_1"))
    gh.rest.pulls.create_review_comment.return_value = resp(NS(node_id="PRRC_1", html_url="http://r/1"))
    # 実行
    res = server.create_review_comment(52, path="src/a.py", line=42, sender="architect", body="指摘です。")
    # 検証
    kwargs = gh.rest.pulls.create_review_comment.call_args.kwargs
    assert kwargs["commit_id"] == "SHA1"
    assert kwargs["line"] == 42
    assert kwargs["side"] == "RIGHT"
    assert res.node_id == "PRRC_1"


def test_normal_when_multi_line(gh, resp):
    """start_line〜line の範囲に紐づく投稿を確認する（正常系・複数行の範囲指定）。"""
    # 準備
    gh.rest.pulls.get.return_value = resp(NS(head=NS(sha="SHA1", ref="feat/x"), node_id="PR_1"))
    gh.rest.pulls.create_review_comment.return_value = resp(NS(node_id="PRRC_1", html_url="u"))
    # 実行
    server.create_review_comment(52, path="src/a.py", line=48, start_line=42, sender="architect", body="範囲指摘。")
    # 検証
    kwargs = gh.rest.pulls.create_review_comment.call_args.kwargs
    assert kwargs["start_line"] == 42 and kwargs["line"] == 48


def test_error_when_out_of_diff(gh, resp, request_failed):
    """diff に含まれない行の指定によるエラーを確認する（異常系・422）。"""
    # 準備
    gh.rest.pulls.get.return_value = resp(NS(head=NS(sha="SHA1", ref="feat/x"), node_id="PR_1"))
    gh.rest.pulls.create_review_comment.side_effect = request_failed(422)
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.create_review_comment(52, path="src/a.py", line=999, sender="architect", body="指摘。")
