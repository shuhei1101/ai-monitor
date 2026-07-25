"""`src/ai_monitor/mcp/server.py` の単体テスト。"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from githubkit.exception import RequestFailed
from mcp import types as mcp_types

import ai_monitor.mcp.server as server
from ai_monitor.mcp.models import (
    AssigneesResult,
    Choice,
    CommentResult,
    CreatedIssueResult,
    CreatedPRResult,
    EmptyResult,
    LabelsResult,
    MonitorAck,
    Question,
    ResolveResult,
    SearchResultItem,
    WorktreeRemoveResult,
)

EXPECTED_TOOLS = {
    "get_issue_or_pr",
    "list_addressed_comments",
    "search_issues_and_prs",
    "comment",
    "ask_questions",
    "reply_comment",
    "resolve_comments",
    "create_review_comment",
    "list_review_threads",
    "resolve_review_threads",
    "add_labels",
    "remove_labels",
    "transition_phase",
    "set_assignee",
    "remove_assignee",
    "update_body",
    "update_title",
    "close",
    "reopen_issue",
    "mark_pr_ready",
    "create_child_issue",
    "create_draft_pr",
    "merge_pr",
    "worktree_create",
    "worktree_remove",
    "report_completion",
    "add_watch_targets",
    "remove_watch_targets",
}


def _resp(data):
    r = MagicMock()
    r.parsed_data = data
    return r


def _request_failed():
    response = MagicMock()
    response.status_code = 404
    return RequestFailed(response)


def _issue_ns(**overrides):
    base = dict(
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
        pull_request=None,
    )
    base.update(overrides)
    return NS(**base)


def _list_tools(app):
    """マウント用 ASGI アプリから登録済みツール一覧を取り出す。"""
    for route in app.routes:
        manager = getattr(getattr(route, "app", None), "session_manager", None)
        if manager is None:
            continue
        handler = manager.app.request_handlers[mcp_types.ListToolsRequest]
        result = asyncio.run(handler(mcp_types.ListToolsRequest(method="tools/list")))
        return result.root.tools
    raise AssertionError("MCP の ASGI アプリがマウントされていない")


# ---- ツール定義群 ----


def test_registered_tools(mon_settings, mon_registry, mcp_agents):
    """全ツールの登録を確認する（正常系）。"""
    # 準備
    app = server.build_mcp_app(mon_settings, registry=mon_registry, agents=mcp_agents)
    # 実行
    names = {t.name for t in _list_tools(app)}
    # 検証
    assert names == EXPECTED_TOOLS


def test_tool_annotations(mon_settings, mon_registry, mcp_agents):
    """読み取り専用 / 破壊的操作のヒント宣言を確認する（正常系）。"""
    # 準備
    app = server.build_mcp_app(mon_settings, registry=mon_registry, agents=mcp_agents)
    # 実行
    tools = {t.name: t for t in _list_tools(app)}
    # 検証
    for name in ("get_issue_or_pr", "list_addressed_comments", "list_review_threads", "search_issues_and_prs"):
        assert tools[name].annotations.readOnlyHint is True
    for name in ("remove_labels", "remove_assignee", "close", "merge_pr", "worktree_remove", "remove_watch_targets"):
        assert tools[name].annotations.destructiveHint is True


# ---- Issue・PR情報取得 ----


def test_get_issue_or_pr(gh, api):
    """スナップショットの組み立てを確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = _resp(_issue_ns())
    # 実行
    snap = api.get_issue_or_pr(
        35, is_pr=False, comments=False, parent=False, sub_issues=False, sub_issues_summary=False
    )
    # 検証
    assert snap.number == 35
    assert snap.title == "プロフィール編集機能"
    assert snap.state == "OPEN"
    assert snap.closed is False
    assert [label.name for label in snap.labels] == ["layer:epic"]
    assert [a.login for a in snap.assignees] == ["shuhei1101"]
    assert snap.author.login == "shuhei1101"


def test_get_issue_or_pr_when_flags_false(gh, api):
    """取得フラグ False のフィールド除外を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = _resp(_issue_ns())
    # 実行
    snap = api.get_issue_or_pr(
        35, is_pr=False, comments=False, parent=False, sub_issues=False, sub_issues_summary=False
    )
    # 検証
    assert snap.comments is None
    gh.rest.issues.list_comments.assert_not_called()


def test_get_issue_or_pr_when_api_error(gh, api):
    """API エラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.issues.get.side_effect = _request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.get_issue_or_pr(35, is_pr=False)


# ---- コメント投稿 ----


def test_comment(gh, api):
    """定型ブロックでの投稿を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = _resp(NS(node_id="IC_1", html_url="http://c/1"))
    # 実行
    res = api.comment(35, is_pr=False, sender="architect", body="設計 Wiki を更新しました。")
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert posted.startswith("> from: @architect")
    assert "設計 Wiki を更新しました。" in posted
    assert res == CommentResult(node_id="IC_1", url="http://c/1")


# ---- 質問投稿 ----


def test_ask_questions(gh, api):
    """選択肢 + 推奨付きの質問投稿を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = _resp(NS(node_id="IC_2", html_url="u"))
    questions = [
        Question(
            question="レスポンス形式は？",
            background="API の返り値を決めたい。",
            choices=[Choice(label="案 A", reason="単純"), Choice(label="案 B", reason="拡張的")],
            recommended_index=0,
            recommended_reason="十分なため",
        ),
        Question(
            question="エラー時のステータスは？",
            background="",
            choices=[Choice(label="400 統一", reason="実装が軽い")],
        ),
    ]
    # 実行
    api.ask_questions(35, is_pr=False, sender="epic-conductor", intro="要件の確認です。", questions=questions)
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert "要件の確認です。" in posted
    assert "レスポンス形式は？" in posted
    assert "案 A" in posted and "案 B" in posted
    assert "推奨" in posted and "十分なため" in posted


def test_ask_questions_when_no_recommendation(gh, api):
    """推奨なし指定時の推奨行の省略を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = _resp(NS(node_id="IC_2", html_url="u"))
    questions = [
        Question(question="Q1", background="", choices=[Choice(label="A1", reason="r")], recommended_index=-1)
    ]
    # 実行
    api.ask_questions(35, is_pr=False, sender="epic-conductor", intro="前置き", questions=questions)
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert "推奨" not in posted


def test_ask_questions_when_empty_intro_and_background(gh, api):
    """空文字セクション（前置き・背景）の省略を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = _resp(NS(node_id="IC_2", html_url="u"))
    questions = [
        Question(question="Q1", background="", choices=[Choice(label="A1", reason="r")], recommended_index=-1)
    ]
    # 実行
    api.ask_questions(35, is_pr=False, sender="epic-conductor", intro="", questions=questions)
    # 検証
    posted = gh.rest.issues.create_comment.call_args.kwargs["body"]
    assert "Q1" in posted
    assert "\n\n\n" not in posted


# ---- コメント返信 ----


def test_reply_comment(gh, api):
    """`---` 区切りでの返信追記を確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = {"node": {"body": "元コメント", "databaseId": 111}}
    gh.rest.issues.update_comment.return_value = _resp(NS(node_id="IC_1", html_url="http://c/1"))
    # 実行
    res = api.reply_comment("IC_1", sender="tester", body="修正しました。")
    # 検証
    kwargs = gh.rest.issues.update_comment.call_args.kwargs
    assert kwargs["comment_id"] == 111
    assert kwargs["body"].startswith("元コメント")
    assert "\n---\n" in kwargs["body"]
    assert "> from: @tester" in kwargs["body"]
    assert res == CommentResult(node_id="IC_1", url="http://c/1")


# ---- コメント一括Resolve ----


def test_resolve_comments(gh, api):
    """複数コメントの一括 Resolve を確認する（正常系）。"""
    # 実行
    res = api.resolve_comments(["IC_1", "IC_2", "IC_3"])
    # 検証
    assert res == ResolveResult(resolved_count=3)
    assert gh.graphql.call_count == 3
    for call_obj, node_id in zip(gh.graphql.call_args_list, ["IC_1", "IC_2", "IC_3"]):
        query, variables = call_obj.args
        assert "minimizeComment" in query and "RESOLVED" in query
        assert variables == {"id": node_id}


# ---- 宛先コメント一覧 ----


def _comment_ns(node_id, body, login):
    return NS(node_id=node_id, body=body, user=NS(login=login), html_url=f"http://c/{node_id}")


def test_list_addressed_comments(gh, api):
    """最終ブロックの宛先での絞り込みを確認する（正常系）。"""
    # 準備
    gh.rest.issues.list_comments.return_value = _resp(
        [
            _comment_ns("IC_1", "> from: @tester\n> to: @architect\n\nテスト作成が完了しました。", "shuhei1101"),
            _comment_ns("IC_2", "> from: @tester\n> to: @implementer\n\n修正してください。", "shuhei1101"),
            _comment_ns("IC_3", "この観点も追加してほしい。", "shuhei1101"),
        ]
    )
    gh.graphql.return_value = {"node": {"isMinimized": False}}
    # 実行
    res = api.list_addressed_comments(52, is_pr=True, addressee="architect")
    # 検証
    assert [c.node_id for c in res] == ["IC_1", "IC_3"]
    assert res[0].blocks[-1].sender == "tester"
    assert res[0].blocks[-1].receiver == "architect"
    assert res[1].blocks[-1].sender is None


def test_list_addressed_comments_when_own_comment(gh, api):
    """自身が投稿したコメント（最後のブロックの from が addressee）の包含を確認する（正常系）。"""
    # 準備
    gh.rest.issues.list_comments.return_value = _resp(
        [_comment_ns("IC_1", "> from: @architect\n> to: @shuhei1101\n\n設計 Wiki を更新しました。", "shuhei1101")]
    )
    gh.graphql.return_value = {"node": {"isMinimized": False}}
    # 実行
    res = api.list_addressed_comments(52, is_pr=True, addressee="architect")
    # 検証
    assert [c.node_id for c in res] == ["IC_1"]
    assert res[0].blocks[-1].sender == "architect"


def test_list_addressed_comments_when_include_resolved(gh, api):
    """Resolved 込みの取得と省略時の除外を確認する（正常系）。"""
    # 準備
    comments = [
        _comment_ns("IC_1", "> from: @tester\n> to: @architect\n\n報告 1", "shuhei1101"),
        _comment_ns("IC_2", "> from: @tester\n> to: @architect\n\n報告 2", "shuhei1101"),
    ]
    gh.rest.issues.list_comments.return_value = _resp(comments)
    gh.graphql.side_effect = [{"node": {"isMinimized": True}}, {"node": {"isMinimized": False}}]
    # 実行
    res = api.list_addressed_comments(52, is_pr=True, addressee="architect", include_resolved=True)
    # 検証
    assert [c.node_id for c in res] == ["IC_1", "IC_2"]
    assert res[0].is_resolved is True
    # 準備
    gh.graphql.side_effect = [{"node": {"isMinimized": True}}, {"node": {"isMinimized": False}}]
    # 実行
    res = api.list_addressed_comments(52, is_pr=True, addressee="architect")
    # 検証
    assert [c.node_id for c in res] == ["IC_2"]


# ---- Issue・PR検索 ----


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


def test_search_issues_and_prs(gh, api):
    """検索結果の変換とリポジトリ絞り込みを確認する（正常系）。"""
    # 準備
    gh.rest.search.issues_and_pull_requests.return_value = _resp(
        NS(
            total_count=2,
            incomplete_results=False,
            items=[
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
    )
    # 実行
    results = api.search_issues_and_prs("プロフィール編集")
    # 検証
    kwargs = gh.rest.search.issues_and_pull_requests.call_args.kwargs
    assert kwargs["q"] == "repo:shuhei1101/ai-monitor-e2e プロフィール編集"
    assert results == [
        SearchResultItem(number=35, is_pr=False, title="プロフィール編集機能", state="open", url="http://i/35"),
        SearchResultItem(number=52, is_pr=True, title="プロフィール編集 API", state="closed", url="http://p/52"),
    ]


def test_search_issues_and_prs_when_sort(gh, api):
    """並び順指定の受け渡しを確認する（正常系）。"""
    # 準備
    gh.rest.search.issues_and_pull_requests.return_value = _resp(
        NS(total_count=0, incomplete_results=False, items=[])
    )
    # 実行
    api.search_issues_and_prs("プロフィール編集", sort="created")
    # 検証
    kwargs = gh.rest.search.issues_and_pull_requests.call_args.kwargs
    assert kwargs["sort"] == "created"
    assert kwargs["order"] == "desc"


def test_search_issues_and_prs_when_no_hit(gh, api):
    """ヒットなしは空配列を確認する（正常系）。"""
    # 準備
    gh.rest.search.issues_and_pull_requests.return_value = _resp(
        NS(total_count=0, incomplete_results=False, items=[])
    )
    # 実行
    results = api.search_issues_and_prs("どこにも無いキーワード")
    # 検証
    assert results == []


# ---- インラインコメント投稿 ----


def test_create_review_comment(gh, api):
    """単一行のインライン投稿を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = _resp(NS(head=NS(sha="SHA1", ref="feat/x"), node_id="PR_1"))
    gh.rest.pulls.create_review_comment.return_value = _resp(NS(node_id="PRRC_1", html_url="http://r/1"))
    # 実行
    res = api.create_review_comment(
        52,
        path="src/ai_monitor/features/agents/service.py",
        line=42,
        sender="architect",
        receiver="implementer",
        body="null チェックを追加してください。",
    )
    # 検証
    kwargs = gh.rest.pulls.create_review_comment.call_args.kwargs
    assert kwargs["commit_id"] == "SHA1"
    assert kwargs["path"] == "src/ai_monitor/features/agents/service.py"
    assert kwargs["line"] == 42
    assert kwargs["side"] == "RIGHT"
    assert kwargs.get("start_line") is None
    assert kwargs["body"].startswith("> from: @architect\n> to: @implementer")
    assert res == CommentResult(node_id="PRRC_1", url="http://r/1")


def test_create_review_comment_when_multi_line(gh, api):
    """範囲指定（start_line）の投稿を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = _resp(NS(head=NS(sha="SHA1", ref="feat/x"), node_id="PR_1"))
    gh.rest.pulls.create_review_comment.return_value = _resp(NS(node_id="PRRC_1", html_url="u"))
    # 実行
    api.create_review_comment(52, path="src/a.py", line=48, start_line=42, sender="architect", body="指摘")
    # 検証
    kwargs = gh.rest.pulls.create_review_comment.call_args.kwargs
    assert kwargs["start_line"] == 42
    assert kwargs["line"] == 48


def test_create_review_comment_when_out_of_diff(gh, api):
    """diff 外の行指定によるエラーの伝播を確認する（異常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = _resp(NS(head=NS(sha="SHA1", ref="feat/x"), node_id="PR_1"))
    gh.rest.pulls.create_review_comment.side_effect = _request_failed()
    # 実行・検証
    with pytest.raises(RequestFailed):
        api.create_review_comment(52, path="src/a.py", line=999, sender="architect", body="指摘")


# ---- レビュースレッド一覧 ----


def _threads_payload(nodes):
    return {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}


def _thread_node(node_id, resolved=False, start_line=None, line=48):
    return {
        "id": node_id,
        "isResolved": resolved,
        "path": "src/a.py",
        "startLine": start_line,
        "line": line,
        "comments": {
            "nodes": [
                {
                    "id": f"{node_id}-c1",
                    "body": "指摘",
                    "author": {"login": "shuhei1101"},
                    "createdAt": "2026-07-20T00:00:00Z",
                    "url": "http://r/1",
                }
            ]
        },
    }


def test_list_review_threads(gh, api):
    """スレッドの変換（単一行 + 範囲の混在）を確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = _threads_payload(
        [_thread_node("PRRT_1", line=42), _thread_node("PRRT_2", start_line=42, line=48)]
    )
    # 実行
    res = api.list_review_threads(52)
    # 検証
    assert [t.node_id for t in res] == ["PRRT_1", "PRRT_2"]
    assert res[0].start_line is None and res[0].line == 42
    assert res[1].start_line == 42 and res[1].line == 48
    assert res[0].path == "src/a.py"
    assert res[0].comments[0].body == "指摘"


def test_list_review_threads_when_resolved_mixed(gh, api):
    """解決済みスレッドの除外を確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = _threads_payload([_thread_node("PRRT_1"), _thread_node("PRRT_2", resolved=True)])
    # 実行
    res = api.list_review_threads(52)
    # 検証
    assert [t.node_id for t in res] == ["PRRT_1"]


def test_list_review_threads_when_include_resolved(gh, api):
    """Resolved 込みの取得を確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = _threads_payload([_thread_node("PRRT_1"), _thread_node("PRRT_2", resolved=True)])
    # 実行
    res = api.list_review_threads(52, include_resolved=True)
    # 検証
    assert [t.node_id for t in res] == ["PRRT_1", "PRRT_2"]
    assert res[1].is_resolved is True


# ---- レビュースレッド一括Resolve ----


def test_resolve_review_threads(gh, api):
    """スレッドの一括解決を確認する（正常系）。"""
    # 実行
    res = api.resolve_review_threads(["PRRT_1", "PRRT_2"])
    # 検証
    assert res == ResolveResult(resolved_count=2)
    assert gh.graphql.call_count == 2
    for call_obj, node_id in zip(gh.graphql.call_args_list, ["PRRT_1", "PRRT_2"]):
        query, variables = call_obj.args
        assert "resolveReviewThread" in query
        assert variables == {"id": node_id}


# ---- ラベル追加 / 除去 / フェーズ遷移 ----


def test_add_labels(gh, api):
    """ラベルの付与と現況返却を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = _resp(NS(labels=[NS(name="layer:epic"), NS(name="確認:tester")]))
    # 実行
    res = api.add_labels(35, is_pr=False, labels=["確認:tester"])
    # 検証
    assert gh.rest.issues.add_labels.call_args.kwargs["labels"] == ["確認:tester"]
    assert res == LabelsResult(current_labels=["layer:epic", "確認:tester"])


def test_remove_labels(gh, api):
    """確認ラベルの除去と現況返却を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = _resp(NS(labels=[NS(name="layer:epic")]))
    # 実行
    res = api.remove_labels(35, is_pr=False, labels=["確認:architect"])
    # 検証
    assert gh.rest.issues.remove_label.call_args.kwargs["name"] == "確認:architect"
    assert res == LabelsResult(current_labels=["layer:epic"])


def test_remove_labels_when_in_discussion(gh, api):
    """`議論中` の除去拒否を確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(ValueError):
        api.remove_labels(35, is_pr=False, labels=["議論中"])
    gh.rest.issues.remove_label.assert_not_called()


def test_transition_phase(gh, api):
    """除去 → 追加の順のラベル一括入れ替えを確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = _resp(NS(labels=[NS(name="layer:subsystem"), NS(name="確認:tester")]))
    # 実行
    res = api.transition_phase(52, is_pr=True, remove_labels_=["確認:architect"], add_labels_=["確認:tester"])
    # 検証
    names = [c[0] for c in gh.rest.issues.method_calls if c[0] in ("remove_label", "add_labels")]
    assert names == ["remove_label", "add_labels"]
    assert res == LabelsResult(current_labels=["layer:subsystem", "確認:tester"])


def test_transition_phase_when_in_discussion(gh, api):
    """`議論中` を含む除去指定の拒否を確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(ValueError):
        api.transition_phase(52, is_pr=True, remove_labels_=["議論中"], add_labels_=["確認:tester"])
    gh.rest.issues.remove_label.assert_not_called()
    gh.rest.issues.add_labels.assert_not_called()


# ---- assignee 設定 / 除去 ----


def test_set_assignee(gh, api):
    """認証ユーザーの assignee 設定を確認する（正常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = _resp(NS(login="shuhei1101"))
    gh.rest.issues.get.return_value = _resp(NS(assignees=[NS(login="shuhei1101")]))
    # 実行
    res = api.set_assignee(35, is_pr=False)
    # 検証
    assert gh.rest.issues.add_assignees.call_args.kwargs["assignees"] == ["shuhei1101"]
    assert res == AssigneesResult(assignees=["shuhei1101"])


def test_remove_assignee(gh, api):
    """認証ユーザーの assignee 除去を確認する（正常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = _resp(NS(login="shuhei1101"))
    gh.rest.issues.get.return_value = _resp(NS(assignees=[]))
    # 実行
    res = api.remove_assignee(35, is_pr=False)
    # 検証
    assert gh.rest.issues.remove_assignees.call_args.kwargs["assignees"] == ["shuhei1101"]
    assert res == AssigneesResult(assignees=[])


# ---- 本文 / タイトル更新・クローズ・再オープン ----


def test_update_body(gh, api):
    """本文の完全置換を確認する（正常系）。"""
    # 実行
    res = api.update_body(35, is_pr=False, body="## 前提条件\n\nなし")
    # 検証
    assert gh.rest.issues.update.call_args.kwargs["body"] == "## 前提条件\n\nなし"
    assert res == EmptyResult()


def test_update_title(gh, api):
    """タイトルの更新を確認する（正常系）。"""
    # 実行
    res = api.update_title(35, is_pr=False, title="プロフィール編集機能")
    # 検証
    assert gh.rest.issues.update.call_args.kwargs["title"] == "プロフィール編集機能"
    assert res == EmptyResult()


def test_close_when_reason_and_delete_branch(gh, api):
    """reason / ブランチ削除付きの PR クローズを確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = _resp(NS(head=NS(ref="feat/x", sha="SHA1")))
    # 実行
    api.close(60, is_pr=True, reason="not_planned", delete_branch=True)
    # 検証
    kwargs = gh.rest.issues.update.call_args.kwargs
    assert kwargs["state"] == "closed"
    assert kwargs["state_reason"] == "not_planned"
    assert gh.rest.git.delete_ref.call_args.kwargs["ref"] == "heads/feat/x"


def test_close_when_issue_with_delete_branch(gh, api):
    """Issue クローズ時の delete_branch 無視を確認する（正常系）。"""
    # 実行
    api.close(50, is_pr=False, delete_branch=True)
    # 検証
    assert gh.rest.issues.update.call_args.kwargs["state"] == "closed"
    gh.rest.git.delete_ref.assert_not_called()


def test_reopen_issue(gh, api):
    """クローズ済み Issue の再オープンを確認する（正常系）。"""
    # 実行
    res = api.reopen_issue(50)
    # 検証
    kwargs = gh.rest.issues.update.call_args.kwargs
    assert kwargs["state"] == "open"
    assert kwargs["state_reason"] == "reopened"
    assert res == EmptyResult()


# ---- Issue / PR 作成・マージ ----


def test_create_child_issue(gh, api):
    """Sub-issue リンク付きの子 Issue 起票を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create.return_value = _resp(NS(number=36, id=999, html_url="http://i/36"))
    # 実行
    res = api.create_child_issue(
        35, title="プロフィールを編集する", body="本文", labels=["layer:story", "確認:story-conductor"]
    )
    # 検証
    assert gh.rest.issues.create.call_args.kwargs["labels"] == ["layer:story", "確認:story-conductor"]
    assert gh.rest.issues.add_sub_issue.call_args.kwargs["issue_number"] == 35
    assert gh.rest.issues.add_sub_issue.call_args.kwargs["sub_issue_id"] == 999
    assert res == CreatedIssueResult(issue_number=36, url="http://i/36", parent_issue_number=35)


def test_create_draft_pr(gh, api):
    """base 明示の Draft PR 作成を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.create.return_value = _resp(NS(number=52, node_id="PR_1", html_url="http://p/52"))
    # 実行
    res = api.create_draft_pr(
        head_branch="feat/backend/profile/edit/edit-api",
        base_branch="feat/story/profile/edit",
        title="プロフィール編集 API",
        body="## 紐づく Issue\n\n- #50",
    )
    # 検証
    kwargs = gh.rest.pulls.create.call_args.kwargs
    assert kwargs["head"] == "feat/backend/profile/edit/edit-api"
    assert kwargs["base"] == "feat/story/profile/edit"
    assert kwargs["draft"] is True
    assert res == CreatedPRResult(pr_number=52, url="http://p/52")


def test_mark_pr_ready(gh, api):
    """markPullRequestReadyForReview mutation での Draft 解除を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = _resp(NS(node_id="PR_1", head=NS(ref="feat/x", sha="S")))
    # 実行
    api.mark_pr_ready(52)
    # 検証
    query, variables = gh.graphql.call_args.args
    assert "markPullRequestReadyForReview" in query
    assert variables == {"id": "PR_1"}


def test_merge_pr(gh, api):
    """既定戦略（squash）でのマージとブランチ削除を確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = _resp(NS(head=NS(ref="feat/x", sha="S")))
    # 実行
    api.merge_pr(52)
    # 検証
    assert gh.rest.pulls.merge.call_args.kwargs["merge_method"] == "squash"
    assert gh.rest.git.delete_ref.call_args.kwargs["ref"] == "heads/feat/x"


def test_merge_pr_when_strategy_given(gh, api):
    """戦略指定でのマージを確認する（正常系）。"""
    # 準備
    gh.rest.pulls.get.return_value = _resp(NS(head=NS(ref="feat/x", sha="S")))
    # 実行
    api.merge_pr(52, strategy="rebase")
    # 検証
    assert gh.rest.pulls.merge.call_args.kwargs["merge_method"] == "rebase"


# ---- worktree 作成 / 削除 ----


def test_worktree_create(tmp_git_repo, api):
    """ブランチ + worktree の作成を確認する（正常系）。"""
    # 実行
    res = api.worktree_create("feat/backend/profile/edit/edit-api")
    # 検証
    worktree = Path(res.worktree_path)
    assert worktree == tmp_git_repo / ".claude" / "worktrees" / "feat-backend-profile-edit-edit-api"
    assert worktree.is_dir()
    assert res.branch == "feat/backend/profile/edit/edit-api"
    branches = subprocess.run(
        ["git", "branch", "--list", res.branch], cwd=tmp_git_repo, capture_output=True, text=True
    ).stdout
    assert res.branch in branches


def test_worktree_create_when_dirs_missing(tmp_git_repo, api):
    """worktree フォルダ未作成時のパス作成を確認する（正常系）。"""
    # 準備
    assert not (tmp_git_repo / ".claude").exists()
    # 実行
    res = api.worktree_create("feat/a")
    # 検証
    assert Path(res.worktree_path).is_dir()


def test_worktree_create_when_remote_branch_exists(tmp_git_repo, api):
    """リモートに現在ブランチがある場合の base ref 解決を確認する（正常系）。"""
    # 実行
    res = api.worktree_create("feat/b")
    # 検証
    assert res.base_ref == "origin/master"


def test_worktree_create_when_remote_branch_missing(tmp_git_repo, api):
    """リモートに現在ブランチが無い場合の HEAD フォールバックを確認する（正常系）。"""
    # 準備
    subprocess.run(["git", "checkout", "-b", "local-only"], cwd=tmp_git_repo, check=True, capture_output=True)
    # 実行
    res = api.worktree_create("feat/c")
    # 検証
    assert res.base_ref == "HEAD"


def test_worktree_create_when_branch_exists(tmp_git_repo, api):
    """既存ブランチ名の指定によるエラーを確認する（異常系）。"""
    # 準備
    api.worktree_create("feat/dup")
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        api.worktree_create("feat/dup")


def test_worktree_remove(tmp_git_repo, api):
    """未マージ commit を持つ worktree + ブランチの強制削除を確認する（正常系）。"""
    # 準備
    created = api.worktree_create("feat/rm")
    worktree = Path(created.worktree_path)
    (worktree / "new.txt").write_text("wip", encoding="utf-8")
    subprocess.run(["git", "add", "new.txt"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "wip"], cwd=worktree, check=True, capture_output=True)
    # 実行
    res = api.worktree_remove("feat/rm")
    # 検証
    assert not worktree.exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "feat/rm"], cwd=tmp_git_repo, capture_output=True, text=True
    ).stdout
    assert "feat/rm" not in branches
    assert res == WorktreeRemoveResult(branch="feat/rm", worktree_path=str(worktree))


def test_worktree_remove_when_worktree_missing(tmp_git_repo, api):
    """worktree 不存在時のエラーを確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(subprocess.CalledProcessError):
        api.worktree_remove("feat/none")


# ---- 内部ヘルパー ----


def test_get_client(tmp_settings):
    """クライアントインスタンスの共有を確認する（正常系）。"""
    # 実行
    first = server._get_client()
    second = server._get_client()
    # 検証
    assert first is second


def test_get_client_when_settings_missing(tmp_path, monkeypatch):
    """設定ファイル不在時のエラーを確認する（異常系）。"""
    # 準備
    monkeypatch.setattr(server, "SETTINGS_PATH", tmp_path / "none.yaml")
    # 実行・検証
    with pytest.raises(FileNotFoundError):
        server._get_client()


def test_get_client_when_token_missing(tmp_path, monkeypatch):
    """github_token 未設定時のエラーを確認する（異常系）。"""
    # 準備
    path = tmp_path / "settings.yaml"
    path.write_text("port: 8765\n", encoding="utf-8")
    monkeypatch.setattr(server, "SETTINGS_PATH", path)
    # 実行・検証
    with pytest.raises(KeyError):
        server._get_client()


def test_get_current_login(gh):
    """認証ユーザーのログイン名解決を確認する（正常系）。"""
    # 準備
    gh.rest.users.get_authenticated.return_value = _resp(NS(login="shuhei1101"))
    # 実行・検証
    assert server._get_current_login() == "shuhei1101"


def test_get_labels(gh):
    """現在ラベル名一覧の取得を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = _resp(NS(labels=[NS(name="layer:epic"), NS(name="確認:epic-conductor")]))
    # 実行・検証
    assert server._get_labels(35, owner="o", repo="r") == ["layer:epic", "確認:epic-conductor"]


def test_get_assignees(gh):
    """現在 assignee 一覧の取得を確認する（正常系）。"""
    # 準備
    gh.rest.issues.get.return_value = _resp(NS(assignees=[NS(login="shuhei1101")]))
    # 実行・検証
    assert server._get_assignees(35, owner="o", repo="r") == ["shuhei1101"]


def test_minimize_comment(gh):
    """minimizeComment mutation の実行を確認する（正常系）。"""
    # 実行
    server._minimize_comment("IC_1")
    # 検証
    query, variables = gh.graphql.call_args.args
    assert "minimizeComment" in query and "RESOLVED" in query
    assert variables == {"id": "IC_1"}


def test_is_minimized(gh):
    """isMinimized の取得を確認する（正常系）。"""
    # 準備
    gh.graphql.return_value = {"node": {"isMinimized": True}}
    # 実行・検証
    assert server._is_minimized("IC_1") is True


def test_create_issue_comment(gh):
    """コメント投稿の実行と結果返却を確認する（正常系）。"""
    # 準備
    gh.rest.issues.create_comment.return_value = _resp(NS(node_id="IC_9", html_url="http://c/9"))
    # 実行
    res = server._create_issue_comment(35, "本文", owner="o", repo="r")
    # 検証
    assert gh.rest.issues.create_comment.call_args.kwargs["body"] == "本文"
    assert res == CommentResult(node_id="IC_9", url="http://c/9")


def test_parse_comment_blocks():
    """from / to ヘッダーと本文の抽出を確認する（正常系）。"""
    # 準備
    body = (
        "> from: @architect\n> to: @implementer\n\nL42 を直してください。\n"
        "\n---\n"
        "> from: @implementer\n> to: @architect\n\n修正しました。\n"
        "\n---\n"
        "> from: @architect\n\n確認しました。"
    )
    # 実行
    blocks = server._parse_comment_blocks(body)
    # 検証
    assert [(b.sender, b.receiver) for b in blocks] == [
        ("architect", "implementer"),
        ("implementer", "architect"),
        ("architect", None),
    ]
    assert blocks[0].body == "L42 を直してください。"


def test_parse_comment_blocks_when_plain_user_comment():
    """ヘッダーなしコメントの宛先なしユーザー投稿扱いを確認する（正常系）。"""
    # 実行
    blocks = server._parse_comment_blocks("この観点も追加してほしい。")
    # 検証
    assert len(blocks) == 1
    assert blocks[0].sender is None and blocks[0].receiver is None
    assert blocks[0].body == "この観点も追加してほしい。"


def test_format_block():
    """from / to ヘッダー付き定型ブロックの組み立てを確認する（正常系）。"""
    # 実行
    out = server._format_block("architect", "implementer", "本文")
    # 検証
    assert out == "> from: @architect\n> to: @implementer\n\n本文"


def test_format_block_when_reply():
    """返信ブロックの先頭 `---` 付与を確認する（正常系）。"""
    # 実行
    out = server._format_block("tester", None, "本文", is_reply=True)
    # 検証
    assert out.startswith("---\n")
    assert "> from: @tester" in out


def test_format_block_when_receiver_none():
    """receiver 省略時の to 行なしを確認する（正常系）。"""
    # 実行
    out = server._format_block("tester", None, "本文")
    # 検証
    assert out == "> from: @tester\n\n本文"


def test_ensure_at():
    """`@` の付与を確認する（正常系）。"""
    # 実行・検証
    assert server._ensure_at("architect") == "@architect"


def test_ensure_at_when_already_prefixed():
    """既に `@` 付きの名前の冪等性を確認する（正常系）。"""
    # 実行・検証
    assert server._ensure_at("@architect") == "@architect"


def test_run_git(tmp_git_repo):
    """git コマンドの実行を確認する（正常系）。"""
    # 実行
    res = server._run_git(["status", "--short"])
    # 検証
    assert res.returncode == 0


def test_repo_root_when_in_worktree(tmp_git_repo, monkeypatch):
    """worktree 内からのメインリポジトリルート解決を確認する（正常系）。"""
    # 準備
    worktree = tmp_git_repo.parent / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-b", "wt-branch", str(worktree)],
        cwd=tmp_git_repo,
        check=True,
        capture_output=True,
    )
    monkeypatch.chdir(worktree)
    # 実行・検証
    assert server._repo_root() == tmp_git_repo


def test_worktree_path(tmp_git_repo):
    """ブランチ名のスラッシュ置換によるパス変換を確認する（正常系）。"""
    # 実行・検証
    assert server._worktree_path("feat/a/b") == tmp_git_repo / ".claude" / "worktrees" / "feat-a-b"


def test_resolve_base_ref(tmp_git_repo):
    """リモート優先の base ref 解決を確認する（正常系）。"""
    # 実行・検証
    assert server._resolve_base_ref() == "origin/master"


# ---- モニター連絡 ----


def test_report_completion(gh_mon, api, mon_registry, session_factory):
    """ラベル除去 + 生存更新を確認する（正常系）。"""
    # 準備
    session_factory("architect", 52)
    before = mon_registry.find("sandbox", "architect", 52).last_seen_at
    # 実行
    res = api.report_completion("architect", 52)
    # 検証
    assert res == MonitorAck(ok=True)
    assert gh_mon.rest.issues.remove_label.call_args.kwargs["name"] == "処理中:architect"
    assert mon_registry.find("sandbox", "architect", 52).last_seen_at != before


def test_report_completion_when_unknown_session(gh_mon, api):
    """セッション不明時のエラーを確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(server.SessionNotFoundError):
        api.report_completion("architect", 52)
    gh_mon.rest.issues.remove_label.assert_not_called()


def test_add_watch_targets(api, mon_registry, session_factory):
    """監視面の追加を確認する（正常系）。"""
    # 準備
    session_factory("architect", 52)
    # 実行
    res = api.add_watch_targets("architect", 52, [60, 61])
    # 検証
    assert res == MonitorAck(ok=True)
    assert mon_registry.find("sandbox", "architect", 52).watch_numbers == [60, 61]


def test_add_watch_targets_when_unknown_session(api):
    """セッション不明時のエラーを確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(server.SessionNotFoundError):
        api.add_watch_targets("architect", 52, [60])


def test_remove_watch_targets(api, mon_registry, session_factory):
    """監視面の除去を確認する（正常系）。"""
    # 準備
    session_factory("architect", 52, watch_numbers=[60, 61])
    # 実行
    res = api.remove_watch_targets("architect", 52, [60])
    # 検証
    assert res == MonitorAck(ok=True)
    assert mon_registry.find("sandbox", "architect", 52).watch_numbers == [61]


def test_remove_watch_targets_when_unknown_session(api):
    """セッション不明時のエラーを確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(server.SessionNotFoundError):
        api.remove_watch_targets("architect", 52, [60])


# ---- プロジェクト解決 ----


def test_resolve_project(mon_settings, mcp_ctx_factory):
    """ヘッダからの解決を確認する（正常系）。"""
    # 実行
    project = server._resolve_project(mcp_ctx_factory("sandbox"), projects=mon_settings.projects)
    # 検証
    assert project.repo == "shuhei1101/ai-monitor-e2e"


def test_resolve_project_when_header_missing(mon_settings, mcp_ctx_factory):
    """ヘッダなし時のエラーを確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(server.ProjectNotFoundError, match="X-Project"):
        server._resolve_project(mcp_ctx_factory(None), projects=mon_settings.projects)


def test_resolve_project_when_unknown_name(mon_settings, mcp_ctx_factory):
    """未登録の名前でのエラーを確認する（異常系）。"""
    # 実行・検証
    with pytest.raises(server.ProjectNotFoundError, match="sandbox"):
        server._resolve_project(mcp_ctx_factory("unknown"), projects=mon_settings.projects)


# ---- アプリ組み立て ----


def test_build_mcp_app(mon_settings, mon_registry, mcp_agents):
    """ツールの登録を確認する（正常系）。"""
    # 実行
    app = server.build_mcp_app(mon_settings, registry=mon_registry, agents=mcp_agents)
    # 検証
    tools = _list_tools(app)
    assert {t.name for t in tools} == EXPECTED_TOOLS
    assert len(tools) == len(EXPECTED_TOOLS)


def test_build_mcp_app_when_signature(mon_settings, mon_registry, mcp_agents):
    """内部引数の除去を確認する（正常系）。"""
    # 実行
    app = server.build_mcp_app(mon_settings, registry=mon_registry, agents=mcp_agents)
    # 検証
    schemas = {t.name: t.inputSchema.get("properties", {}) for t in _list_tools(app)}
    for name, properties in schemas.items():
        assert {"ctx", "settings", "registry", "agents"}.isdisjoint(properties), name
    assert "number" in schemas["report_completion"]



def test_log_tool_call(caplog):
    """戻り値の素通しと実行ログを確認する（正常系）。"""
    # 準備
    @server._log_tool_call
    def sample_tool(number: int) -> str:
        return f"ok:{number}"

    # 実行
    with caplog.at_level("INFO"):
        result = sample_tool(35)
    # 検証
    assert result == "ok:35"
    assert "tool=sample_tool" in caplog.text
    assert "number=35" in caplog.text


def test_log_tool_call_when_tool_raises(caplog):
    """例外の再送出と失敗ログを確認する（異常系）。"""
    # 準備
    @server._log_tool_call
    def sample_tool(number: int) -> str:
        raise ValueError("失敗")

    # 実行・検証
    with caplog.at_level("WARNING"), pytest.raises(ValueError, match="失敗"):
        sample_tool(35)
    assert "MCP ツールが失敗しました" in caplog.text
    assert "tool=sample_tool" in caplog.text
