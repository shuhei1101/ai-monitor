"""「DraftPR作成」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import CreatedPRResult


def test_normal(gh, resp):
    """Draft + base 指定での PR 作成と番号 / URL 返却を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.create.return_value = resp(NS(number=52, node_id="PR_1", html_url="http://p/52"))
    # 実行
    res = server.create_draft_pr(
        head_branch="feat/backend/profile/edit/edit-api",
        base_branch="feat/story/profile/edit",
        title="プロフィール編集 API",
        body="## 紐づく Issue\n\n- #50",
    )
    # 検証
    kwargs = gh.rest.pulls.create.call_args.kwargs
    assert kwargs["draft"] is True
    assert kwargs["base"] == "feat/story/profile/edit"
    assert res == CreatedPRResult(pr_number=52, url="http://p/52")


def test_error_when_api_error(gh, request_failed):
    """未 push ブランチ等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.pulls.create.side_effect = request_failed(422)
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.create_draft_pr(head_branch="feat/none", base_branch="master", title="T", body="B")
