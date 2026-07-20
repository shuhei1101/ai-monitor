"""「質問投稿」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import Choice, Question


def _questions() -> list[Question]:
    return [
        Question(
            question="レスポンス形式は？",
            background="返り値を決めたい。",
            choices=[Choice(label="案 A", reason="単純"), Choice(label="案 B", reason="拡張的")],
            recommended_index=0,
            recommended_reason="十分なため",
        )
    ]


def test_normal(gh, resp):
    """質問リストの本文組み立て → 定型ブロック化 → REST 投稿の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = resp(NS(node_id="IC_2", html_url="http://c/2"))
    # 実行
    res = server.ask_questions(
        35, is_pr=False, sender="epic-conductor", intro="要件の確認です。", questions=_questions()
    )
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert posted.startswith("> from: @epic-conductor")
    assert "## レスポンス形式は？" in posted
    assert "- A. 案 A: 単純" in posted
    assert "推奨: A. 案 A — 十分なため" in posted
    assert res.node_id == "IC_2"


def test_error_when_api_error(gh, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.create_comment.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.ask_questions(35, is_pr=False, sender="epic-conductor", intro="", questions=_questions())
