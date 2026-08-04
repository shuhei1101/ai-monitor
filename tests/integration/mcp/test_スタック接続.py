"""「スタック接続」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import StackLinkResult


def _stack_entry(number: int, position: int) -> dict:
    return {"position": position, "pullRequest": {"number": number, "state": "OPEN"}}


def _wire_stacks(gh_mon, membership: dict[int, tuple[int, list[int]]]):
    """PR 番号 → (スタック番号, 構成 PR) の所属を graphql 応答として配線する。"""

    def _graphql(query, variables=None):
        number = variables["number"]
        if number not in membership:
            return {"repository": {"pullRequest": {"stackEntry": None, "stack": None}}}
        stack_number, members = membership[number]
        return {
            "repository": {
                "pullRequest": {
                    "stackEntry": {"position": members.index(number) + 1},
                    "stack": {
                        "number": stack_number,
                        "entries": {
                            "nodes": [_stack_entry(n, i + 1) for i, n in enumerate(members)]
                        },
                    },
                }
            }
        }

    gh_mon.graphql.side_effect = _graphql


def test_normal(gh_mon, api):
    """全 PR が未所属のときの新規スタック作成を確認する（正常系）。"""
    # 準備: どの PR もスタックに属していない
    _wire_stacks(gh_mon, {})
    gh_mon.request.return_value.json.return_value = {"number": 123}
    # 実行
    res = api.link_stack([120, 121, 122])
    # 検証
    assert res == StackLinkResult(linked=True, stack_number=123, reason=None)
    method, path = gh_mon.request.call_args.args
    assert (method, path) == ("POST", "/repos/shuhei1101/ai-monitor-e2e/stacks")
    assert gh_mon.request.call_args.kwargs["json"] == {"pull_requests": [120, 121, 122]}


def test_normal_when_existing_stack(gh_mon, api):
    """既存スタックの上端への追加を確認する（正常系・底が既存スタックに属する場合）。"""
    # 準備: 底の 120 だけがスタック 123 に属している
    _wire_stacks(gh_mon, {120: (123, [120])})
    # 実行
    res = api.link_stack([120, 121])
    # 検証: 未所属の 121 だけが積まれ、既存のスタック番号が返る
    assert res == StackLinkResult(linked=True, stack_number=123, reason=None)
    method, path = gh_mon.request.call_args.args
    assert (method, path) == ("POST", "/repos/shuhei1101/ai-monitor-e2e/stacks/123/add")
    assert gh_mon.request.call_args.kwargs["json"] == {"pull_requests": [121]}


def test_normal_when_other_stack(gh_mon, api):
    """別スタックに属する PR が混ざるときの見送りを確認する（正常系・繋げない場合）。"""
    # 準備: 120 と 121 が別々のスタックに属する（1 PR は 1 スタックまで）
    _wire_stacks(gh_mon, {120: (123, [120]), 121: (124, [121])})
    # 実行
    res = api.link_stack([120, 121])
    # 検証: 例外にせず理由を返し、作成も追加も行わない
    assert res.linked is False
    assert res.stack_number is None
    assert res.reason
    gh_mon.request.assert_not_called()


def test_error_when_api_error(gh_mon, api, request_failed):
    """base 連鎖の不整合による API エラーの伝播を確認する（異常系）。"""
    # 準備: スタック作成が 422 を返す
    _wire_stacks(gh_mon, {})
    gh_mon.request.side_effect = request_failed(422)
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.link_stack([120, 121])
