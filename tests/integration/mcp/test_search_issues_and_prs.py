"""「Issue・PR検索」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed

import server
from models import SearchResultItem


def _search_resp(resp, items):
    return resp(NS(total_count=len(items), incomplete_results=False, items=items))


def _search_item_ns(**overrides):
    base = dict(
        number=35,
        title="プロフィール編集機能",
        state="open",
        html_url="http://i/35",
        pull_request=None,
    )
    base.update(overrides)
    return NS(**base)


def test_normal(gh, resp, fake_remote):
    """キーワード検索 → 一覧返却の一連を確認する（正常系）。"""
    # 準備
    gh.rest.search.issues_and_pull_requests.return_value = _search_resp(
        resp,
        [
            _search_item_ns(),
            _search_item_ns(
                number=52,
                title="プロフィール編集 API",
                state="closed",
                html_url="http://p/52",
                pull_request=NS(merged_at=None),
            ),
        ],
    )
    # 実行
    results = server.search_issues_and_prs("プロフィール編集")
    # 検証
    kwargs = gh.rest.search.issues_and_pull_requests.call_args.kwargs
    assert kwargs["q"] == "repo:shuhei1101/ai-monitor-e2e プロフィール編集"
    assert results == [
        SearchResultItem(number=35, is_pr=False, title="プロフィール編集機能", state="open", url="http://i/35"),
        SearchResultItem(number=52, is_pr=True, title="プロフィール編集 API", state="closed", url="http://p/52"),
    ]


def test_normal_when_sorted(gh, resp, fake_remote):
    """`sort` 指定が検索 API に渡り新しい順で返ることを確認する（正常系）。"""
    # 準備
    gh.rest.search.issues_and_pull_requests.return_value = _search_resp(
        resp,
        [
            _search_item_ns(number=52, title="新しい Issue", html_url="http://i/52"),
            _search_item_ns(number=35, title="古い Issue", html_url="http://i/35"),
        ],
    )
    # 実行
    results = server.search_issues_and_prs("Issue", sort="created")
    # 検証
    kwargs = gh.rest.search.issues_and_pull_requests.call_args.kwargs
    assert kwargs["sort"] == "created"
    assert kwargs["order"] == "desc"
    assert [r.number for r in results] == [52, 35]


def test_normal_when_no_hit(gh, resp, fake_remote):
    """該当なしで空配列を返すことを確認する（正常系）。"""
    # 準備
    gh.rest.search.issues_and_pull_requests.return_value = _search_resp(resp, [])
    # 実行
    results = server.search_issues_and_prs("どこにも無いキーワード")
    # 検証
    assert results == []


def test_error_when_api_error(gh, request_failed, fake_remote):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.search.issues_and_pull_requests.side_effect = request_failed(403)
    # 実行・検証
    with pytest.raises(RequestFailed):
        server.search_issues_and_prs("プロフィール編集")
