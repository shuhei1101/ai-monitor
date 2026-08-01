"""「質問投稿」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from ai_monitor.mcp.models import Choice, Question


def _questions(count: int = 3) -> list[Question]:
    return [
        Question(
            question=f"論点 {i + 1} をどうしますか？",
            background="判断の背景。",
            choices=[Choice(label="案 A", reason="単純"), Choice(label="案 B", reason="拡張的")],
            recommended_index=0,
            recommended_reason="十分なため",
        )
        for i in range(count)
    ]


def test_normal(gh, resp, api):
    """質問ごとの本文組み立て → 定型ブロック化 → 件数分の REST 投稿を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.side_effect = [
        resp(NS(node_id=f"IC_{i}", html_url=f"http://c/{i}")) for i in range(3)
    ]
    # 実行
    res = api.ask_questions(
        35, is_pr=False, sender="epic-conductor", receiver="shuhei1101", questions=_questions()
    )
    # 検証
    assert gh.rest.issues.create_comment.call_count == 3
    bodies = [c.kwargs["body"] for c in gh.rest.issues.create_comment.call_args_list]
    for i, body in enumerate(bodies):
        assert body.startswith("> from: @epic-conductor")
        assert "> to: @shuhei1101" in body
        assert f"## 論点 {i + 1} をどうしますか？" in body
        assert "- A. 案 A: 単純" in body
        assert "推奨: A. 案 A — 十分なため" in body
        assert body.endswith("---\n")
    assert [c.node_id for c in res.comments] == ["IC_0", "IC_1", "IC_2"]
    assert [c.url for c in res.comments] == ["http://c/0", "http://c/1", "http://c/2"]


def test_error_when_api_error(gh, request_failed, api):
    """1 件目の投稿失敗で中断することを確認する（異常系）。"""
    # 準備
    gh.rest.issues.create_comment.side_effect = request_failed(404)
    # 実行・検証
    with pytest.raises(RuntimeError, match="0 / 3"):
        api.ask_questions(35, is_pr=False, sender="epic-conductor", questions=_questions())
    assert gh.rest.issues.create_comment.call_count == 1


def test_error_when_partial_failure(gh, resp, request_failed, api):
    """途中の投稿失敗で投稿済みが残ることを確認する（異常系）。"""
    # 準備
    gh.rest.issues.create_comment.side_effect = [
        resp(NS(node_id="IC_0", html_url="http://c/0")),
        request_failed(500),
    ]
    # 実行・検証
    with pytest.raises(RuntimeError, match="1 / 3"):
        api.ask_questions(35, is_pr=False, sender="epic-conductor", questions=_questions())
    # 1 件目は投稿済みのまま残り、3 件目は試行されない
    assert gh.rest.issues.create_comment.call_count == 2
