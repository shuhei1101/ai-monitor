"""`src/ai_monitor/integrations/github/stacks.py` の単体テスト。"""
from __future__ import annotations

import pytest
from githubkit.exception import RequestFailed

from ai_monitor.integrations.github import stacks


def _entry(number: int, position: int, state: str = "OPEN") -> dict:
    return {"position": position, "pullRequest": {"number": number, "state": state}}


def _graphql_result(position: int, entries: list[dict], stack_number: int = 90) -> dict:
    return {
        "repository": {
            "pullRequest": {
                "stackEntry": {"position": position},
                "stack": {"number": stack_number, "entries": {"nodes": entries}},
            }
        }
    }


def test_get_stack(gh_mon, mon_project):
    """所属ありのスタック取得を確認する（正常系）。"""
    # 準備: 3 件のスタックの上端（position=3）
    gh_mon.graphql.return_value = _graphql_result(
        3, [_entry(120, 1), _entry(121, 2), _entry(122, 3)]
    )
    # 実行
    stack = stacks.get_stack(mon_project, 122)
    # 検証
    assert stack.number == 90
    assert stack.position == 3
    assert stack.pull_requests == [120, 121, 122]
    assert stack.below_open == [120, 121]
    variables = gh_mon.graphql.call_args.args[1]
    assert variables == {"owner": "shuhei1101", "repo": "ai-monitor-e2e", "number": 122}


def test_get_stack_when_not_stacked(gh_mon, mon_project):
    """未所属で None が返ることを確認する（正常系）。"""
    # 準備
    gh_mon.graphql.return_value = {
        "repository": {"pullRequest": {"stackEntry": None, "stack": None}}
    }
    # 実行
    stack = stacks.get_stack(mon_project, 122)
    # 検証
    assert stack is None


def test_get_stack_when_below_merged(gh_mon, mon_project):
    """下位が全て merged のとき下位 open が空になることを確認する（正常系）。"""
    # 準備: 下位 2 件が merged（起動可能の判定に使う）
    gh_mon.graphql.return_value = _graphql_result(
        3, [_entry(120, 1, "MERGED"), _entry(121, 2, "MERGED"), _entry(122, 3)]
    )
    # 実行
    stack = stacks.get_stack(mon_project, 122)
    # 検証
    assert stack.below_open == []
    assert stack.pull_requests == [120, 121, 122]


def test_create_stack(gh_mon, mon_project):
    """スタック作成を確認する（正常系）。"""
    # 準備
    gh_mon.request.return_value.json.return_value = {"number": 123}
    # 実行
    number = stacks.create_stack(mon_project, [120, 121])
    # 検証
    assert number == 123
    method, path = gh_mon.request.call_args.args
    assert (method, path) == ("POST", "/repos/shuhei1101/ai-monitor-e2e/stacks")
    assert gh_mon.request.call_args.kwargs["json"] == {"pull_requests": [120, 121]}


def test_create_stack_when_base_broken(gh_mon, mon_project, request_failed):
    """base 連鎖の不整合で例外が伝播することを確認する（異常系）。"""
    # 準備
    gh_mon.request.side_effect = request_failed(422)
    # 実行・検証
    with pytest.raises(RequestFailed):
        stacks.create_stack(mon_project, [120, 121])


def test_add_to_stack(gh_mon, mon_project):
    """既存スタックの上端への追加を確認する（正常系）。"""
    # 実行
    stacks.add_to_stack(mon_project, 123, [122])
    # 検証
    method, path = gh_mon.request.call_args.args
    assert (method, path) == ("POST", "/repos/shuhei1101/ai-monitor-e2e/stacks/123/add")
    assert gh_mon.request.call_args.kwargs["json"] == {"pull_requests": [122]}


def test_dissolve_stack(gh_mon, mon_project):
    """スタック解散を確認する（正常系）。"""
    # 実行
    stacks.dissolve_stack(mon_project, 123, [122])
    # 検証
    method, path = gh_mon.request.call_args.args
    assert (method, path) == ("POST", "/repos/shuhei1101/ai-monitor-e2e/stacks/123/unstack")
    assert gh_mon.request.call_args.kwargs["json"] == {"pull_requests": [122]}


def test_dissolve_stack_when_dissolved(gh_mon, mon_project, request_failed):
    """解散済みスタックで例外が伝播することを確認する（異常系）。"""
    # 準備
    gh_mon.request.side_effect = request_failed(404)
    # 実行・検証
    with pytest.raises(RequestFailed):
        stacks.dissolve_stack(mon_project, 123, [122])
