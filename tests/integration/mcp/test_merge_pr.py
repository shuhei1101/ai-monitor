"""「PRマージ」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import EmptyResult


def test_normal(gh, resp):
    """マージ戦略解決 → マージ + head ブランチ削除の一連を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = resp(NS(head=NS(ref="feat/x", sha="S")))
    # 実行
    res = server.merge_pr(52)
    # 検証
    assert gh.rest.pulls.merge.call_args.kwargs["merge_method"] == "squash"
    assert gh.rest.git.delete_ref.call_args.kwargs["ref"] == "heads/feat/x"
    assert res == EmptyResult()


def test_error_when_conflict(gh, request_failed):
    """コンフリクト（405）等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.pulls.merge.side_effect = request_failed(405)
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.merge_pr(52)
