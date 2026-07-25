"""「レビュースレッド一括Resolve」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import GraphQLFailed

from ai_monitor.mcp.models import ResolveResult


def test_normal(gh, api):
    """node_id ごとの resolveReviewThread 実行を確認する（正常系）。"""
    # 実行
    res = api.resolve_review_threads(["PRRT_1", "PRRT_2"])
    # 検証
    assert res == ResolveResult(resolved_count=2)
    assert gh.graphql.call_count == 2


def test_error_when_invalid_node_id(gh, graphql_failed, api):
    """node_id 不正による GraphQL エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.graphql.side_effect = graphql_failed()
    # 実行・検証
    with pytest.raises(GraphQLFailed):
        api.resolve_review_threads(["PRRT_bad"])
