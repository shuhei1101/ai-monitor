"""「レビュースレッド一覧」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import GraphQLFailed



def _payload(nodes):
    return {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}


def _node(node_id, resolved=False, body="> from: @architect\n> to: @implementer\n\n指摘"):
    return {
        "id": node_id,
        "isResolved": resolved,
        "path": "src/a.py",
        "startLine": None,
        "line": 42,
        "comments": {
            "nodes": [
                {
                    "id": f"{node_id}-c1",
                    "body": body,
                    "diffHunk": "@@ -40,3 +40,4 @@\n+added",
                    "author": {"login": "x"},
                    "createdAt": "t",
                    "url": "u",
                }
            ]
        },
    }


def test_normal(gh, api):
    """スレッド取得 → 解決済み除外 → 最後のコメントでの自分宛判定の一連を確認する（正常系）。"""
    # 準備: 自分宛 / 解決済み / 他エージェント宛 / ユーザーの宛先なし返信
    gh.graphql.return_value = _payload(
        [
            _node("PRRT_1"),
            _node("PRRT_2", resolved=True),
            _node("PRRT_3", body="> from: @architect\n> to: @tester\n\n他人宛の指摘"),
            _node("PRRT_4", body="ここも直しておいて"),
        ]
    )
    # 実行
    res = api.list_review_threads(52, addressee="implementer")
    # 検証
    # 解決済み（PRRT_2）だけが落ち、宛先違い（PRRT_3）も is_addressed=False で返る
    assert [t.node_id for t in res] == ["PRRT_1", "PRRT_3", "PRRT_4"]
    assert [t.is_addressed for t in res] == [True, False, True]
    assert res[0].comments[0].body.endswith("指摘")
    assert res[0].comments[0].diff_hunk == "@@ -40,3 +40,4 @@\n+added"


def test_normal_when_include_resolved(gh, api):
    """include_resolved=true での全スレッド返却を確認する（正常系・解決済みを含める）。"""
    # 準備
    gh.graphql.return_value = _payload([_node("PRRT_1"), _node("PRRT_2", resolved=True)])
    # 実行
    res = api.list_review_threads(52, addressee="implementer", include_resolved=True)
    # 検証
    assert [t.node_id for t in res] == ["PRRT_1", "PRRT_2"]


def test_error_when_api_error(gh, graphql_failed, api):
    """PR 不存在等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.graphql.side_effect = graphql_failed()
    # 実行・検証
    with pytest.raises(GraphQLFailed):
        api.list_review_threads(999, addressee="implementer")
