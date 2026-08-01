"""「コメント投稿」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import (
    CommentResult,
    CommitEntry,
    CommitsFormat,
    PageRangeEntry,
    PagesFormat,
    PlainFormat,
)


def test_normal(gh, resp, api):
    """定型ブロック組み立て → REST 投稿の一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    # 実行
    res = api.comment(
        35, is_pr=False, sender="architect", receiver="shuhei1101",
        format=PlainFormat(body="設計を更新しました。"),
    )
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert posted.startswith("> from: @architect\n> to: @shuhei1101")
    assert "設計を更新しました。" in posted
    # ユーザーがそのまま書き足せるよう末尾が区切り線で終わる
    assert posted.endswith("------\n")
    assert res == CommentResult(node_id="IC_1", url="http://c/1")


def test_normal_when_commits_format(gh, resp, api):
    """commit 表を本文末尾に足して投稿することを確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    fmt = CommitsFormat(
        body="テスト作成が完了しました。",
        entries=[
            CommitEntry(commit="a1b2c3d", summary="ユーザー編集の結合テストを追加"),
            CommitEntry(commit="e4f5g6h", summary="異常系ケースを追加"),
        ],
    )
    # 実行
    api.comment(40, is_pr=True, sender="tester", receiver="architect", format=fmt)
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert "| commit | 内容 |" in posted
    # 行が entries の順に並び、commit ID がバッククォートで囲まれている
    assert posted.index("`a1b2c3d`") < posted.index("`e4f5g6h`")
    # 表は本文末尾（区切り線の手前）に入る
    assert posted.endswith("------\n")
    assert posted.index("`e4f5g6h`") < posted.rindex("------")


def test_normal_when_pages_format(gh, resp, api):
    """ページ範囲表を本文末尾に足して投稿することを確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    fmt = PagesFormat(
        body="以下の設計でテストを作成してください。",
        entries=[
            PageRangeEntry(page="docs/wiki/設計図/インターフェース定義/バックエンド/ユーザー登録.py.md", commit="a1b2c3d"),
            PageRangeEntry(
                page="docs/wiki/設計図/モジュール構成/バックエンド/ユーザー.py.md",
                start_commit="e4f5g6h",
                commit="i7j8k9l",
            ),
        ],
    )
    # 実行
    api.comment(40, is_pr=True, sender="architect", receiver="tester", format=fmt)
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert "| 対象ページ | commit 範囲 |" in posted
    # start_commit なしは commit 単体・ありは start_commit..commit の範囲セルになる
    assert "| `docs/wiki/設計図/インターフェース定義/バックエンド/ユーザー登録.py.md` | `a1b2c3d` |" in posted
    assert "| `docs/wiki/設計図/モジュール構成/バックエンド/ユーザー.py.md` | `e4f5g6h..i7j8k9l` |" in posted


def test_error_when_empty_entries(gh, resp, api):
    """表を持つ形式で行が空のときのエラーを確認する（異常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = resp(NS(node_id="IC_1", html_url="http://c/1"))
    # 実行・検証
    with pytest.raises(ValueError, match="1 件以上"):
        api.comment(35, is_pr=False, sender="architect", format=CommitsFormat(body="本文", entries=[]))
    assert gh.rest.issues.create_comment.call_count == 0


def test_error_when_api_error(gh, request_failed, api):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.create_comment.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.comment(35, is_pr=False, sender="architect", format=PlainFormat(body="本文"))
