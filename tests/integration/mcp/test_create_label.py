"""「ラベル作成」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import CreatedLabelResult


def _request_failed(status_code: int) -> RequestFailed:
    response = MagicMock()
    response.status_code = status_code
    return RequestFailed(response)


def test_normal(gh, resp, api):
    """未作成のラベルの作成を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_label.return_value = resp(NS(name="scope:backend"))
    # 実行
    res = api.create_label("scope:backend", color="c2e0c6", description="担当サブシステム")
    # 検証
    kwargs = gh.rest.issues.create_label.call_args.kwargs
    assert kwargs["owner"] == "shuhei1101" and kwargs["repo"] == "ai-monitor-e2e"
    assert kwargs["name"] == "scope:backend"
    assert kwargs["color"] == "c2e0c6"
    assert kwargs["description"] == "担当サブシステム"
    assert res == CreatedLabelResult(name="scope:backend", created=True)


def test_normal_when_exists(gh, api):
    """同名が既にあるときに何もしないことを確認する（正常系）。"""
    # 準備: 作成 API が同名衝突の 422 を返す
    gh.rest.issues.create_label.side_effect = _request_failed(422)
    # 実行
    res = api.create_label("scope:backend", color="c2e0c6", description="担当サブシステム")
    # 検証
    assert res == CreatedLabelResult(name="scope:backend", created=False)
    # 既存を上書きしない（更新 API を呼ばない）
    assert gh.rest.issues.update_label.call_count == 0


def test_error_when_api_error(gh, api):
    """権限不足の伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.create_label.side_effect = _request_failed(403)
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.create_label("scope:backend", color="c2e0c6")
