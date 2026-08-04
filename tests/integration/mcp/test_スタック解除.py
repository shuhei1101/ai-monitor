"""「スタック解除」の結合テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.mcp.models import StackUnlinkResult


def _wire_stack(gh_mon, members: list[int] | None, stack_number: int = 123):
    """対象 PR のスタック所属を graphql 応答として配線する（None は未所属）。"""

    def _graphql(query, variables=None):
        if members is None:
            return {"repository": {"pullRequest": {"stackEntry": None, "stack": None}}}
        number = variables["number"]
        return {
            "repository": {
                "pullRequest": {
                    "stackEntry": {"position": members.index(number) + 1},
                    "stack": {
                        "number": stack_number,
                        "entries": {
                            "nodes": [
                                {"position": i + 1, "pullRequest": {"number": n, "state": "OPEN"}}
                                for i, n in enumerate(members)
                            ]
                        },
                    },
                }
            }
        }

    gh_mon.graphql.side_effect = _graphql


def _paths(gh_mon):
    return [call.args[1] for call in gh_mon.request.call_args_list]


def test_normal(gh_mon, api):
    """解除と残りの組み直しを確認する（正常系）。"""
    # 準備: 3 件のスタックの上端を外す
    _wire_stack(gh_mon, [120, 121, 122])
    gh_mon.request.return_value.json.return_value = {"number": 124}
    # 実行
    res = api.unlink_stack(122)
    # 検証: 解除 → 残り 2 件で作成の順
    assert res == StackUnlinkResult(unlinked=True, restacked=[120, 121], stack_number=124)
    assert _paths(gh_mon) == [
        "/repos/shuhei1101/ai-monitor-e2e/stacks/123/unstack",
        "/repos/shuhei1101/ai-monitor-e2e/stacks",
    ]
    assert gh_mon.request.call_args.kwargs["json"] == {"pull_requests": [120, 121]}


def test_normal_when_one_left(gh_mon, api):
    """残りが 1 件のときに組み直さないことを確認する（正常系・残りが 1 件）。"""
    # 準備: スタックは 2 件以上必要なので組み直せない
    _wire_stack(gh_mon, [120, 122])
    # 実行
    res = api.unlink_stack(122)
    # 検証
    assert res == StackUnlinkResult(unlinked=True, restacked=[], stack_number=None)
    assert _paths(gh_mon) == ["/repos/shuhei1101/ai-monitor-e2e/stacks/123/unstack"]


def test_normal_when_not_stacked(gh_mon, api):
    """未所属の読み飛ばしを確認する（正常系・スタック未所属）。"""
    # 準備: どのスタックにも属していない（マージ手順から無条件に呼べるようにする）
    _wire_stack(gh_mon, None)
    # 実行
    res = api.unlink_stack(122)
    # 検証: 例外にせず何もしない
    assert res == StackUnlinkResult(unlinked=False, restacked=[], stack_number=None)
    gh_mon.request.assert_not_called()


def test_error_when_api_error(gh_mon, api, request_failed):
    """解散済みスタックによる API エラーの伝播を確認する（異常系）。"""
    # 準備: 解除が 404 を返す
    _wire_stack(gh_mon, [120, 121, 122])
    gh_mon.request.side_effect = request_failed(404)
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.unlink_stack(122)
    # 組み直しへは進まない
    assert _paths(gh_mon) == ["/repos/shuhei1101/ai-monitor-e2e/stacks/123/unstack"]
