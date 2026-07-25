"""「コメント一括Resolve」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import GraphQLFailed

from ai_monitor.mcp.models import ResolveResult


def test_normal(gh, api):
    """node_id ごとの minimizeComment 実行を確認する（正常系）。"""
    # 実行
    res = api.resolve_comments(["IC_1", "IC_2", "IC_3"])
    # 検証
    assert res == ResolveResult(resolved_count=3)
    assert gh.graphql.call_count == 3


def test_error_when_midway_failure(gh, graphql_failed, api):
    """途中失敗時はそこまでの件数だけ Resolve されエラーが伝播することを確認する（異常系）。"""
    # 準備
    gh.graphql.side_effect = [{"minimizeComment": {}}, graphql_failed()]
    # 実行・検証
    with pytest.raises(GraphQLFailed):
        api.resolve_comments(["IC_1", "IC_bad", "IC_3"])
    assert gh.graphql.call_count == 2
