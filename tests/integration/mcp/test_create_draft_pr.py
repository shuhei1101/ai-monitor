"""「DraftPR作成」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import CreatedPRResult


def test_normal(gh, resp, api):
    """Draft + base 指定での PR 作成とラベル付与を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.create.return_value = resp(NS(number=52, node_id="PR_1", html_url="http://p/52"))
    # 実行
    res = api.create_draft_pr(
        head_branch="feat/backend/profile/edit/edit-api",
        base_branch="feat/story/profile/edit",
        title="プロフィール編集 API",
        body="## 紐づく Issue\n\n- #50",
        labels=["layer:subsystem"],
    )
    # 検証
    kwargs = gh.rest.pulls.create.call_args.kwargs
    assert kwargs["draft"] is True
    assert kwargs["base"] == "feat/story/profile/edit"
    # PR 作成 API はラベルを受け取らないので Issue として付与する
    label_kwargs = gh.rest.issues.add_labels.call_args.kwargs
    assert (label_kwargs["issue_number"], label_kwargs["labels"]) == (52, ["layer:subsystem"])
    assert res == CreatedPRResult(pr_number=52, url="http://p/52")


def test_normal_when_no_labels(gh, resp, api):
    """ラベルを省略したときに付与 API を呼ばないことを確認する（正常系）。"""
    # 準備
    gh.rest.pulls.create.return_value = resp(NS(number=52, node_id="PR_1", html_url="http://p/52"))
    # 実行
    res = api.create_draft_pr(
        head_branch="feat/backend/profile/edit/edit-api",
        base_branch="feat/story/profile/edit",
        title="プロフィール編集 API",
        body="## 紐づく Issue\n\n- #50",
    )
    # 検証
    gh.rest.issues.add_labels.assert_not_called()
    assert res == CreatedPRResult(pr_number=52, url="http://p/52")


def test_error_when_api_error(gh, request_failed, api):
    """未 push ブランチ等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.pulls.create.side_effect = request_failed(422)
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.create_draft_pr(head_branch="feat/none", base_branch="master", title="T", body="B")
