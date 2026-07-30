"""「コメント返信」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import GraphQLFailed

from ai_monitor.mcp.models import CommitEntry, CommitsFormat, PlainFormat


def test_normal_when_ends_with_separator(gh, resp, api):
    """既存本文が区切り線で終わっているときの追記を確認する（正常系）。"""
    # 準備
    existing = "> from: @architect\n\n設計を更新しました。\n\n---\n"
    gh.graphql.return_value = {"node": {"body": existing, "databaseId": 111}}
    gh.rest.issues.update_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    # 実行
    res = api.reply_comment("IC_1", sender="tester", format=PlainFormat(body="修正しました。"))
    # 検証
    posted = gh.rest.issues.update_comment.call_args.kwargs["body"]
    # 既存本文は変化せず、その末尾に from ヘッダー付きの追記ブロックが足される
    assert posted.startswith(existing)
    assert "> from: @tester" in posted
    # 境目の区切り線は既存の 1 本だけ（追記側は先頭に --- を足さない）
    assert posted.count("---") == 2
    assert posted.endswith("---\n")
    assert res.node_id == "IC_1"


def test_normal_when_not_ends_with_separator(gh, resp, api):
    """既存本文が区切り線で終わっていないときの追記を確認する（正常系）。"""
    # 準備
    existing = "元コメント\n\n---\n\nこの観点も追加してほしい。"
    gh.graphql.return_value = {"node": {"body": existing, "databaseId": 111}}
    gh.rest.issues.update_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    # 実行
    res = api.reply_comment("IC_1", sender="tester", format=PlainFormat(body="修正しました。"))
    # 検証
    kwargs = gh.rest.issues.update_comment.call_args.kwargs
    assert kwargs["comment_id"] == 111
    # 既存本文は変化せず、--- 区切り + from ヘッダー付きの追記ブロックが足される
    assert kwargs["body"] == f"{existing}\n\n---\n> from: @tester\n\n修正しました。\n\n---\n"
    assert res.node_id == "IC_1"


def test_normal_when_table_format(gh, resp, api):
    """format.type に応じた表を追記ブロックの末尾に足すことを確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = {"node": {"body": "元コメント\n\n---\n", "databaseId": 111}}
    gh.rest.issues.update_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    fmt = CommitsFormat(
        body="指摘 3 件に対応しました。",
        entries=[
            CommitEntry(commit="a1b2c3d", summary="異常系ケースを追加"),
            CommitEntry(commit="e4f5g6h", summary="観点の抜けを補完"),
        ],
    )
    # 実行
    api.reply_comment("IC_1", sender="tester", receiver="architect", format=fmt)
    # 検証
    posted = gh.rest.issues.update_comment.call_args.kwargs["body"]
    # 表の書式（列名・セルの装飾・行順）がコメント投稿と同一になる
    assert "| commit | 内容 |" in posted
    assert "| `a1b2c3d` | 異常系ケースを追加 |" in posted
    assert posted.index("`a1b2c3d`") < posted.index("`e4f5g6h`")
    # 表は追記ブロックの末尾（区切り線の手前）に入る
    assert posted.endswith("---\n")
    assert posted.index("`e4f5g6h`") < posted.rindex("---")


def test_error_when_api_error(gh, graphql_failed, api):
    """node_id 不正等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.graphql.side_effect = graphql_failed()
    # 実行・検証
    with pytest.raises(GraphQLFailed):
        api.reply_comment("IC_bad", sender="tester", format=PlainFormat(body="本文"))
