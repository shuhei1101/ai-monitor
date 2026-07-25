"""「本文更新」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import EmptyResult


def test_normal(gh, api):
    """body の完全置換更新を確認する（正常系）。"""
    # 実行
    res = api.update_body(35, is_pr=False, body="## 前提条件\n\nなし")
    # 検証
    assert gh.rest.issues.update.call_args.kwargs["body"] == "## 前提条件\n\nなし"
    assert res == EmptyResult()


def test_error_when_api_error(gh, request_failed, api):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.update.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.update_body(35, is_pr=False, body="本文")
