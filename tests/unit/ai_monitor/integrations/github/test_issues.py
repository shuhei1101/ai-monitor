"""`src/ai_monitor/integrations/github/issues.py` の単体テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import ai_monitor.integrations.github.issues as issues_mod
from ai_monitor.shared.types import PullRequest


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
        )
    )
    # 実行
    issue = issues_mod.get_issue(mon_project, 35)
    # 検証
    assert issue.number == 35
    assert issue.state == "closed"
    assert issue.labels == ["layer:epic"]


def test_get_parent_number(mon_project):
    """base を head に持つ PR を親として返すことを確認する（正常系）。"""
    # 準備
    targets = [
        PullRequest(number=10, base_ref="master", head_ref="feat/epic/x"),
        PullRequest(number=20, base_ref="feat/epic/x", head_ref="feat/story/x/y"),
    ]
    # 実行 / 検証
    assert issues_mod.get_parent_number(mon_project, 20, targets) == 10


def test_get_parent_number_when_no_parent(mon_project):
    """親が一覧に無い場合に None を返すことを確認する（正常系）。"""
    targets = [PullRequest(number=10, base_ref="master", head_ref="feat/epic/x")]
    assert issues_mod.get_parent_number(mon_project, 10, targets) is None


def test_list_child_numbers():
    """base に自分の head を持つ PR を子として返すことを確認する（正常系）。"""
    # 準備
    targets = [
        PullRequest(number=10, base_ref="master", head_ref="feat/epic/x"),
        PullRequest(number=20, base_ref="feat/epic/x", head_ref="docs/epic/x/mock"),
        PullRequest(number=21, base_ref="feat/epic/x", head_ref="feat/story/x/y"),
        PullRequest(number=30, base_ref="feat/story/x/y", head_ref="feat/be/x/y"),
    ]
    # 実行 / 検証（1 段のみ。孫は含まない）
    assert issues_mod.list_child_numbers(10, targets) == [20, 21]


def test_list_child_numbers_when_no_children():
    """子が無い場合に空リストを返すことを確認する（正常系）。"""
    targets = [PullRequest(number=10, base_ref="master", head_ref="feat/epic/x")]
    assert issues_mod.list_child_numbers(10, targets) == []
