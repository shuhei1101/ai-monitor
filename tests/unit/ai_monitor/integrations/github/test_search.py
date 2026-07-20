"""`src/ai_monitor/integrations/github/search.py` の単体テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import ai_monitor.integrations.github.search as search_mod
from ai_monitor.shared.types import Issue, PullRequest


def _resp(data):
    r = MagicMock()
    r.parsed_data = data
    return r


def _issue_ns(number, **overrides):
    base = dict(
        number=number,
        state="open",
        labels=[NS(name="layer:epic")],
        assignees=[NS(login="shuhei1101")],
        body="本文",
        pull_request=None,
        sub_issues_summary=None,
    )
    base.update(overrides)
    return NS(**base)


def test_list_open_targets_when_multi_page(gh_mon, mon_project):
    """ページ跨ぎの全件取得を確認する（正常系）。"""
    # 準備
    page1 = [_issue_ns(n) for n in range(1, 101)]
    page2 = [_issue_ns(101)]
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp(page1), _resp(page2)]
    # 実行
    targets = search_mod.list_open_targets(mon_project)
    # 検証
    assert len(targets) == 101
    assert gh_mon.rest.issues.list_for_repo.call_args_list[0].kwargs["state"] == "open"


def test_list_open_targets_when_pr_mixed(gh_mon, mon_project):
    """Issue / PR の判別変換を確認する（正常系）。"""
    # 準備
    issue = _issue_ns(35)
    pr = _issue_ns(52, labels=[NS(name="確認:tester")], pull_request=NS(url="http://p/52"), body="## 紐づく Issue\n\n- #50")
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([issue, pr])]
    # 実行
    targets = search_mod.list_open_targets(mon_project)
    # 検証
    assert isinstance(targets[0], Issue)
    assert isinstance(targets[1], PullRequest)
    assert targets[1].linked_issue_numbers == [50]
    assert targets[1].labels == ["確認:tester"]


def test_list_open_targets_when_sub_issues_summary(gh_mon, mon_project):
    """Sub-issue 件数の変換を確認する（正常系）。"""
    # 準備
    issue = _issue_ns(30, sub_issues_summary=NS(total=2, completed=1))
    gh_mon.rest.issues.list_for_repo.side_effect = [_resp([issue])]
    # 実行
    targets = search_mod.list_open_targets(mon_project)
    # 検証
    assert targets[0].sub_issues_total == 2
    assert targets[0].sub_issues_completed == 1


def test_parse_linked_issue_numbers():
    """番号の抽出を確認する（正常系）。"""
    # 実行
    numbers = search_mod._parse_linked_issue_numbers("## 紐づく Issue\n\n- #50\n- #51\n")
    # 検証
    assert numbers == [50, 51]


def test_parse_linked_issue_numbers_when_section_missing():
    """セクションなしは空を確認する（正常系）。"""
    # 実行
    numbers = search_mod._parse_linked_issue_numbers("## 概要\n\n本文のみ。\n")
    # 検証
    assert numbers == []


def test_parse_linked_issue_numbers_when_duplicated():
    """重複の排除を確認する（正常系）。"""
    # 実行
    numbers = search_mod._parse_linked_issue_numbers("## 紐づく Issue\n\n- #50\n- #50\n")
    # 検証
    assert numbers == [50]
