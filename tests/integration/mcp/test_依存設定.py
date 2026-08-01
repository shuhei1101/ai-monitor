"""「依存設定」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import GraphQLFailed


def _node(number: int, state: str = "OPEN") -> dict:
    return {"number": number, "title": f"依存先 #{number}", "url": f"http://i/{number}", "state": state}


def _wire(gh, blocked_after: list[dict]):
    """node_id 解決・mutation・操作後の取得を 1 つの graphql スタブで捌く。"""
    calls: list[str] = []

    def _graphql(query, variables=None):
        if "blockedBy" in query:
            return {"repository": {"issue": {"id": "I_52", "blockedBy": {"nodes": blocked_after}}}}
        if "addBlockedBy" in query or "removeBlockedBy" in query:
            calls.append("add" if "addBlockedBy" in query else "remove")
            return {"addBlockedBy": {"issue": {"number": 52}}}
        # node_id 解決
        return {"repository": {"issue": {"id": f"I_{variables['number']}"}}}

    gh.graphql.side_effect = _graphql
    return calls


def test_normal(gh, api):
    """依存の設定と操作後の一覧返却を確認する（正常系）。"""
    # 準備: 依存先 2 件（片方は closed）
    calls = _wire(gh, [_node(48, "CLOSED"), _node(49)])
    # 実行
    res = api.set_blocked_by(52, blocking_numbers=[48, 49])
    # 検証
    assert calls == ["add", "add"]
    assert [(b.number, b.state) for b in res.blocked_by] == [(48, "CLOSED"), (49, "OPEN")]


def test_normal_when_remove(gh, api):
    """remove=true での解除を確認する（正常系・解除）。"""
    # 準備: 解除後は 1 件だけ残る
    calls = _wire(gh, [_node(49)])
    # 実行
    res = api.set_blocked_by(52, blocking_numbers=[48], remove=True)
    # 検証
    assert calls == ["remove"]
    assert [b.number for b in res.blocked_by] == [49]


def test_error_when_api_error(gh, graphql_failed, api):
    """Issue 不存在等の API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.graphql.side_effect = graphql_failed()
    # 実行・検証
    with pytest.raises(GraphQLFailed):
        api.set_blocked_by(999, blocking_numbers=[48])
