"""「クローズ」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import EmptyResult


def test_normal(gh):
    """state=closed での更新を確認する（正常系）。"""
    # 実行
    res = server.close(50, is_pr=False)
    # 検証
    kwargs = gh.rest.issues.update.call_args.kwargs
    assert kwargs["state"] == "closed"
    assert "state_reason" not in kwargs
    gh.rest.git.delete_ref.assert_not_called()
    assert res == EmptyResult()


def test_normal_when_reason_given(gh):
    """Issue の reason 指定時のフラグ組み立てを確認する（正常系・Issue の reason 指定時）。"""
    # 実行
    server.close(50, is_pr=False, reason="not_planned")
    # 検証
    assert gh.rest.issues.update.call_args.kwargs["state_reason"] == "not_planned"


def test_normal_when_delete_branch(gh, resp):
    """PR の delete_branch 指定時のブランチ削除を確認する（正常系・PR の delete_branch 指定時）。"""
    # 準備
    gh.rest.pulls.get.return_value = resp(NS(head=NS(ref="feat/x", sha="SHA1")))
    # 実行
    server.close(60, is_pr=True, delete_branch=True)
    # 検証
    assert gh.rest.git.delete_ref.call_args.kwargs["ref"] == "heads/feat/x"


def test_error_when_api_error(gh, request_failed):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.update.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.close(50, is_pr=False)
