"""`src/ai_monitor/integrations/github/issues.py` の単体テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import ai_monitor.integrations.github.issues as issues_mod


def _resp(data):
    r = MagicMock()
    r.parsed_data = data
    return r


def test_close_issue(gh_mon, mon_project):
    """completed クローズを確認する（正常系）。"""
    # 実行
    issues_mod.close_issue(mon_project, 34)
    # 検証
    kwargs = gh_mon.rest.issues.update.call_args.kwargs
    assert kwargs["issue_number"] == 34
    assert kwargs["state"] == "closed"
    assert kwargs["state_reason"] == "completed"


def test_get_issue(gh_mon, mon_project):
    """closed 状態の変換を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.get.return_value = _resp(
        NS(
            number=35,
            state="closed",
            labels=[NS(name="layer:epic")],
            assignees=[],
            body="本文",
            pull_request=None,
            sub_issues_summary=NS(total=1, completed=1),
        )
    )
    # 実行
    issue = issues_mod.get_issue(mon_project, 35)
    # 検証
    assert issue.number == 35
    assert issue.state == "closed"
    assert issue.labels == ["layer:epic"]
    assert issue.sub_issues_total == 1


def test_get_parent_number(gh_mon, mon_project):
    """親番号の取得を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.get_parent.return_value = _resp(NS(number=30))
    # 実行
    number = issues_mod.get_parent_number(mon_project, 35)
    # 検証
    assert number == 30


def test_get_parent_number_when_no_parent(gh_mon, mon_project, request_failed):
    """親なしは None を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.get_parent.side_effect = request_failed(404)
    # 実行
    number = issues_mod.get_parent_number(mon_project, 35)
    # 検証
    assert number is None


def test_list_sub_issue_numbers(gh_mon, mon_project):
    """子番号の取得を確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_sub_issues.side_effect = [_resp([NS(number=40), NS(number=41)])]
    # 実行
    numbers = issues_mod.list_sub_issue_numbers(mon_project, 35)
    # 検証
    assert numbers == [40, 41]


def test_list_sub_issue_numbers_when_no_children(gh_mon, mon_project):
    """子なしは空リストを確認する（正常系）。"""
    # 準備
    gh_mon.rest.issues.list_sub_issues.side_effect = [_resp([])]
    # 実行
    numbers = issues_mod.list_sub_issue_numbers(mon_project, 35)
    # 検証
    assert numbers == []
