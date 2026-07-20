"""「レビュースレッド一覧」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import GraphQLFailed

import server


def _payload(nodes):
    return {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}


def _node(node_id, resolved=False):
    return {
        "id": node_id,
        "isResolved": resolved,
        "path": "src/a.py",
        "startLine": None,
        "line": 42,
        "comments": {"nodes": [{"id": f"{node_id}-c1", "body": "指摘", "author": {"login": "x"}, "createdAt": "t", "url": "u"}]},
    }


def test_normal(gh):
    """スレッド取得 → 解決済み除外の一連を確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = _payload([_node("PRRT_1"), _node("PRRT_2", resolved=True)])
    # 実行
    res = server.list_review_threads(52)
    # 検証
    assert [t.node_id for t in res] == ["PRRT_1"]
    assert res[0].comments[0].body == "指摘"


def test_normal_when_include_resolved(gh):
    """include_resolved=true での全スレッド返却を確認する（正常系・解決済みを含める）。"""
    # 準備
    gh.graphql.return_value = _payload([_node("PRRT_1"), _node("PRRT_2", resolved=True)])
    # 実行
    res = server.list_review_threads(52, include_resolved=True)
    # 検証
    assert [t.node_id for t in res] == ["PRRT_1", "PRRT_2"]


def test_error_when_api_error(gh, graphql_failed):
    """PR 不存在等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.graphql.side_effect = graphql_failed()
    # 実行・検証
    with pytest.raises(GraphQLFailed):
        server.list_review_threads(999)
