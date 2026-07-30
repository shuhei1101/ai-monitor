"""「PRマージ」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import EmptyResult


def test_normal(gh, resp, api, monkeypatch):
    """マージ可否の確定待ち → マージ + head ブランチ削除の一連を確認する（正常系）。"""
    # 準備
    import ai_monitor.mcp.server as server

    monkeypatch.setattr(server.time, "sleep", lambda _: None)
    gh.rest.pulls.get.side_effect = [
        resp(NS(head=NS(ref="feat/x", sha="S"), mergeable=None)),
        resp(NS(head=NS(ref="feat/x", sha="S"), mergeable=True)),
    ]
    # 実行
    res = api.merge_pr(52)
    # 検証
    assert gh.rest.pulls.get.call_count == 2
    assert gh.rest.pulls.merge.call_count == 1
    assert gh.rest.pulls.merge.call_args.kwargs["merge_method"] == "squash"
    assert gh.rest.git.delete_ref.call_args.kwargs["ref"] == "heads/feat/x"
    assert res == EmptyResult()


def test_error_when_conflict(gh, request_failed, api):
    """コンフリクト（405）等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.pulls.merge.side_effect = request_failed(405)
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.merge_pr(52)
