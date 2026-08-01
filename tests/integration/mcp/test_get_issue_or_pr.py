"""「Issue・PR情報取得」の結合テスト。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from githubkit.exception import RequestFailed



def test_normal(gh, resp, api):
    """Issue を取得してスナップショットを組み立てる一連を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = resp(
        NS(
            number=35,
            title="プロフィール編集機能",
            body="本文",
            html_url="http://i/35",
            state="open",
            state_reason=None,
            closed_at=None,
            created_at="2026-07-01T00:00:00Z",
            updated_at="2026-07-02T00:00:00Z",
            labels=[NS(name="layer:epic", id=1, color="1d76db", description=None)],
            assignees=[NS(login="shuhei1101")],
            user=NS(login="shuhei1101"),
            sub_issues_summary=NS(total=2, completed=1, percent_completed=50.0),
        )
    )
    gh.rest.issues.list_comments.return_value = resp(
        [NS(node_id="IC_1", body="こんにちは", user=NS(login="shuhei1101"), html_url="http://c/1", created_at="t")]
    )
    # GraphQL はコメントの Resolved 判定と blockedBy の取得で使い分けられる
    def _graphql(query, variables=None):
        if "blockedBy" in query:
            return {
                "repository": {
                    "issue": {
                        "id": "I_35",
                        "blockedBy": {
                            "nodes": [
                                {"number": 30, "title": "先行 Issue", "url": "http://i/30", "state": "OPEN"}
                            ]
                        },
                    }
                }
            }
        return {"node": {"isMinimized": False}}

    gh.graphql.side_effect = _graphql
    gh.rest.issues.get_parent.return_value = resp(NS(number=12, title="親", html_url="http://i/12", state="open"))
    gh.rest.issues.list_sub_issues.return_value = resp(
        [NS(number=36, title="子", html_url="http://i/36", state="open")]
    )
    # 実行
    snap = api.get_issue_or_pr(35, is_pr=False)
    # 検証
    assert snap.state == "OPEN"
    assert snap.parent.number == 12
    assert [s.number for s in snap.sub_issues] == [36]
    assert snap.sub_issues_summary.total == 2
    # 着手をブロックしている Issue が状態付きで返る
    assert [(b.number, b.state) for b in snap.blocked_by] == [(30, "OPEN")]
    assert snap.comments[0].id == "IC_1"
    assert snap.comments[0].is_minimized is False
    assert snap.head_ref is None
    assert snap.base_ref is None


def test_normal_when_pr(gh, resp, api):
    """PR を取得して head / base ブランチ名を含むスナップショットを組み立てる一連を確認する（正常系・PR 指定）。"""
    # 準備
    gh.rest.pulls.get.return_value = resp(
        NS(
            number=157,
            title="タスク編集 バックエンド",
            body="## 紐づく Issue",
            html_url="http://p/157",
            state="open",
            merged_at=None,
            closed_at=None,
            created_at="2026-07-01T00:00:00Z",
            updated_at="2026-07-02T00:00:00Z",
            labels=[NS(name="layer:subsystem", id=1, color="5319e7", description=None)],
            assignees=[],
            user=NS(login="shuhei1101"),
            head=NS(ref="feat/backend/task-edit-154/update-api"),
            base=NS(ref="feat/story/task-edit-154"),
        )
    )
    gh.rest.issues.list_comments.return_value = resp([])
    # 実行
    snap = api.get_issue_or_pr(157, is_pr=True)
    # 検証
    assert snap.head_ref == "feat/backend/task-edit-154/update-api"
    assert snap.base_ref == "feat/story/task-edit-154"
    assert snap.parent is None
    assert snap.sub_issues is None
    assert snap.sub_issues_summary is None


def test_error_when_api_error(gh, request_failed, api):
    """API エラー（対象不存在 等）の伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.get.side_effect = request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.get_issue_or_pr(999, is_pr=False)
