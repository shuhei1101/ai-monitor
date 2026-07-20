"""GitHub API を叩く MCP ツール全 23 本の外部疎通テスト（sandbox 実測）。"""
from __future__ import annotations

import pytest
from githubkit.exception import RequestFailed

import server
from models import Choice, Question


def _last_comment_body(gh_live, repo_ctx, number: int) -> str:
    owner, repo = repo_ctx
    return gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=number).parsed_data[-1].body


# ---- Issue・PR情報取得 ----


def test_ext_get_issue_or_pr_when_issue(issue_factory, gh_live, repo_ctx):
    """Issue を全フィールドで取得し親子 Issue の解決を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    parent = issue_factory("外部疎通テスト 親")
    child = issue_factory("外部疎通テスト 子")
    gh_live.rest.issues.add_sub_issue(owner=owner, repo=repo, issue_number=parent.number, sub_issue_id=child.id)
    # 実行
    child_snap = server.get_issue_or_pr(child.number, is_pr=False)
    parent_snap = server.get_issue_or_pr(parent.number, is_pr=False)
    # 検証
    assert child_snap.state == "OPEN"
    assert child_snap.parent.number == parent.number
    assert [s.number for s in parent_snap.sub_issues] == [child.number]
    assert parent_snap.sub_issues_summary.total == 1


def test_ext_get_issue_or_pr_when_pr(pr_factory, gh_live, repo_ctx):
    """is_pr=True で PR を取得し MERGED 判定と isMinimized を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    pr = pr_factory(draft=False)
    posted = server.comment(pr.number, is_pr=True, sender="architect", body="外部疎通テスト用コメント")
    server.resolve_comments([posted.node_id])
    gh_live.rest.pulls.merge(owner=owner, repo=repo, pull_number=pr.number, merge_method="squash")
    # 実行
    snap = server.get_issue_or_pr(pr.number, is_pr=True)
    # 検証
    assert snap.state == "MERGED"
    minimized = {c.id: c.is_minimized for c in snap.comments}
    assert minimized[posted.node_id] is True


# ---- コメント ----


def test_ext_comment(issue_factory, gh_live, repo_ctx):
    """定型ブロックでのコメント投稿を確認する（正常系）。"""
    # 準備
    issue = issue_factory()
    # 実行
    res = server.comment(issue.number, is_pr=False, sender="architect", body="外部疎通テストの投稿です。")
    # 検証
    assert res.node_id.startswith("IC_")
    assert res.url
    body = _last_comment_body(gh_live, repo_ctx, issue.number)
    assert body.startswith("> from: @architect")


def test_ext_ask_questions(issue_factory, gh_live, repo_ctx):
    """選択肢 + 推奨マーク付きの質問投稿を確認する（正常系）。"""
    # 準備
    issue = issue_factory()
    questions = [
        Question(
            question="レスポンス形式は？",
            background="外部疎通テスト用の質問。",
            choices=[Choice(label="案 A", reason="単純"), Choice(label="案 B", reason="拡張的")],
            recommended_index=0,
            recommended_reason="十分なため",
        )
    ]
    # 実行
    res = server.ask_questions(
        issue.number, is_pr=False, sender="epic-conductor", intro="確認です。", questions=questions
    )
    # 検証
    assert res.node_id.startswith("IC_")
    body = _last_comment_body(gh_live, repo_ctx, issue.number)
    assert "- A. 案 A" in body
    assert "推奨: A" in body


def test_ext_reply_comment(issue_factory, gh_live, repo_ctx):
    """既存コメントへの `---` 区切り追記を確認する（正常系）。"""
    # 準備
    issue = issue_factory()
    first = server.comment(issue.number, is_pr=False, sender="architect", body="最初の投稿。")
    # 実行
    res = server.reply_comment(first.node_id, sender="tester", body="返信です。")
    # 検証
    assert res.node_id == first.node_id
    body = _last_comment_body(gh_live, repo_ctx, issue.number)
    assert "\n---\n" in body
    assert "> from: @tester" in body


def test_ext_resolve_comments(issue_factory):
    """minimizeComment の実行で isMinimized が true になることを確認する（正常系）。"""
    # 準備
    issue = issue_factory()
    posted = server.comment(issue.number, is_pr=False, sender="architect", body="Resolve 対象。")
    # 実行
    res = server.resolve_comments([posted.node_id])
    # 検証
    assert res.resolved_count == 1
    assert server._is_minimized(posted.node_id) is True


def test_ext_list_addressed_comments(issue_factory, gh_live, repo_ctx):
    """to 行の宛先判定と isMinimized の取得を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    issue = issue_factory()
    addressed = server.comment(issue.number, is_pr=False, sender="tester", receiver="architect", body="報告です。")
    server.comment(issue.number, is_pr=False, sender="architect", receiver="tester", body="宛先違い。")
    plain = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=issue.number, body="ユーザーの素のコメント。"
    ).parsed_data
    # 実行
    res = server.list_addressed_comments(issue.number, is_pr=False, addressee="architect")
    # 検証
    assert [c.node_id for c in res] == [addressed.node_id, plain.node_id]
    assert res[0].blocks[-1].receiver == "architect"
    assert res[0].is_resolved is False


def test_ext_search_issues_and_prs():
    """キーワード検索の実行と SearchResultItem 構造を確認する（正常系）。"""
    # 実行
    results = server.search_issues_and_prs("is:issue", sort="created", limit=5)
    # 検証
    assert isinstance(results, list)
    for item in results:
        assert item.number > 0
        assert item.is_pr is False
        assert item.state in ("open", "closed")
        assert item.url.startswith("https://github.com/")


# ---- インラインコメント / レビュースレッド ----


def test_ext_create_review_comment_when_single_line(pr_factory):
    """単一行のインライン投稿を確認する（正常系）。"""
    # 準備
    pr = pr_factory()
    # 実行
    res = server.create_review_comment(
        pr.number, path=f"{pr.head.ref}.txt", line=1, sender="architect", receiver="implementer", body="単一行の指摘。"
    )
    # 検証
    assert res.node_id.startswith("PRRC_")


def test_ext_create_review_comment_when_multi_line(pr_factory):
    """範囲（start_line〜line）の投稿を確認する（正常系）。"""
    # 準備
    pr = pr_factory()
    # 実行
    res = server.create_review_comment(
        pr.number, path=f"{pr.head.ref}.txt", line=3, start_line=1, sender="architect", body="範囲の指摘。"
    )
    # 検証
    assert res.node_id.startswith("PRRC_")


def test_ext_list_review_threads(pr_factory):
    """レビュースレッドの取得を確認する（正常系）。"""
    # 準備
    pr = pr_factory()
    server.create_review_comment(
        pr.number, path=f"{pr.head.ref}.txt", line=3, start_line=1, sender="architect", body="スレッド確認用。"
    )
    # 実行
    threads = server.list_review_threads(pr.number)
    # 検証
    assert len(threads) == 1
    assert threads[0].node_id.startswith("PRRT_")
    assert threads[0].path == f"{pr.head.ref}.txt"
    assert threads[0].start_line == 1
    assert threads[0].line == 3
    assert threads[0].is_resolved is False


def test_ext_resolve_review_threads(pr_factory):
    """resolveReviewThread でスレッドが解決済みになることを確認する（正常系）。"""
    # 準備
    pr = pr_factory()
    server.create_review_comment(pr.number, path=f"{pr.head.ref}.txt", line=1, sender="architect", body="解決対象。")
    thread_id = server.list_review_threads(pr.number)[0].node_id
    # 実行
    res = server.resolve_review_threads([thread_id])
    # 検証
    assert res.resolved_count == 1
    threads = server.list_review_threads(pr.number, include_resolved=True)
    assert threads[0].is_resolved is True


# ---- ラベル / assignee ----


def test_ext_add_labels(issue_factory):
    """定義済みラベルの付与と現況返却を確認する（正常系）。"""
    # 準備
    issue = issue_factory()
    # 実行
    res = server.add_labels(issue.number, is_pr=False, labels=["bug"])
    # 検証
    assert "bug" in res.current_labels


def test_ext_remove_labels(issue_factory, gh_live, repo_ctx):
    """ラベルの除去と現況返却を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    issue = issue_factory()
    gh_live.rest.issues.add_labels(owner=owner, repo=repo, issue_number=issue.number, labels=["bug"])
    # 実行
    res = server.remove_labels(issue.number, is_pr=False, labels=["bug"])
    # 検証
    assert "bug" not in res.current_labels


def test_ext_transition_phase(issue_factory, gh_live, repo_ctx):
    """除去 → 付与の順のラベル入れ替えと現況返却を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    issue = issue_factory()
    gh_live.rest.issues.add_labels(owner=owner, repo=repo, issue_number=issue.number, labels=["bug"])
    # 実行
    res = server.transition_phase(issue.number, is_pr=False, remove_labels_=["bug"], add_labels_=["documentation"])
    # 検証
    assert "bug" not in res.current_labels
    assert "documentation" in res.current_labels


def test_ext_set_assignee(issue_factory):
    """認証ユーザーの assignee 設定と現況返却を確認する（正常系）。"""
    # 準備
    issue = issue_factory()
    login = server._get_current_login()
    # 実行
    res = server.set_assignee(issue.number, is_pr=False)
    # 検証
    assert res.assignees == [login]


def test_ext_remove_assignee(issue_factory, gh_live, repo_ctx):
    """認証ユーザーの assignee 除去と現況返却を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    issue = issue_factory()
    login = server._get_current_login()
    gh_live.rest.issues.add_assignees(owner=owner, repo=repo, issue_number=issue.number, assignees=[login])
    # 実行
    res = server.remove_assignee(issue.number, is_pr=False)
    # 検証
    assert res.assignees == []


# ---- 本文・状態 ----


def test_ext_update_body(issue_factory, gh_live, repo_ctx):
    """Markdown 本文の完全置換を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    issue = issue_factory()
    # 実行
    server.update_body(issue.number, is_pr=False, body="## 前提条件\n\nなし")
    # 検証
    updated = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=issue.number).parsed_data
    assert updated.body == "## 前提条件\n\nなし"


def test_ext_update_title(issue_factory, gh_live, repo_ctx):
    """タイトルの更新を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    issue = issue_factory()
    # 実行
    server.update_title(issue.number, is_pr=False, title="外部疎通テスト 更新後タイトル")
    # 検証
    updated = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=issue.number).parsed_data
    assert updated.title == "外部疎通テスト 更新後タイトル"


def test_ext_close_when_issue_not_planned(issue_factory, gh_live, repo_ctx):
    """reason=not_planned での Issue クローズを確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    issue = issue_factory()
    # 実行
    server.close(issue.number, is_pr=False, reason="not_planned")
    # 検証
    closed = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=issue.number).parsed_data
    assert closed.state == "closed"
    assert closed.state_reason == "not_planned"


def test_ext_close_when_pr_delete_branch(pr_factory, gh_live, repo_ctx):
    """delete_branch=True での PR クローズと head ブランチ削除を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    pr = pr_factory()
    # 実行
    server.close(pr.number, is_pr=True, delete_branch=True)
    # 検証
    closed = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr.number).parsed_data
    assert closed.state == "closed"
    with pytest.raises(RequestFailed):
        gh_live.rest.git.get_ref(owner=owner, repo=repo, ref=f"heads/{pr.head.ref}")


def test_ext_reopen_issue(issue_factory, gh_live, repo_ctx):
    """クローズ済み Issue の再オープンを確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    issue = issue_factory()
    gh_live.rest.issues.update(owner=owner, repo=repo, issue_number=issue.number, state="closed")
    # 実行
    server.reopen_issue(issue.number)
    # 検証
    reopened = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=issue.number).parsed_data
    assert reopened.state == "open"
    assert reopened.state_reason == "reopened"


# ---- Issue / PR 作成・マージ ----


def test_ext_create_child_issue(issue_factory, gh_live, repo_ctx):
    """子 Issue の REST ID での親リンク付き起票を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    parent = issue_factory("外部疎通テスト 起票親")
    # 実行
    res = server.create_child_issue(
        parent.number, title="外部疎通テスト 起票子", body="自動クローズ予定", labels=["documentation"]
    )
    # 検証
    linked_parent = gh_live.rest.issues.get_parent(owner=owner, repo=repo, issue_number=res.issue_number).parsed_data
    assert linked_parent.number == parent.number
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=res.issue_number, state="closed", state_reason="not_planned"
    )


def test_ext_create_draft_pr(branch_factory, gh_live, repo_ctx):
    """draft=true / base 指定での PR 作成を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    branch = branch_factory()
    # 実行
    res = server.create_draft_pr(
        head_branch=branch, base_branch="master", title="外部疎通テスト Draft PR", body="## 紐づく Issue\n\n- #1"
    )
    # 検証
    created = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=res.pr_number).parsed_data
    assert created.draft is True
    assert created.base.ref == "master"
    gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=res.pr_number, state="closed")


def test_ext_mark_pr_ready(pr_factory, gh_live, repo_ctx):
    """markPullRequestReadyForReview で isDraft が false になることを確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    pr = pr_factory(draft=True)
    # 実行
    server.mark_pr_ready(pr.number)
    # 検証
    updated = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr.number).parsed_data
    assert updated.draft is False


def test_ext_merge_pr_when_squash(pr_factory, gh_live, repo_ctx):
    """squash マージと head ブランチ削除を確認する（正常系）。"""
    # 準備
    owner, repo = repo_ctx
    pr = pr_factory(draft=False)
    # 実行
    server.merge_pr(pr.number)
    # 検証
    merged = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr.number).parsed_data
    assert merged.merged is True
    with pytest.raises(RequestFailed):
        gh_live.rest.git.get_ref(owner=owner, repo=repo, ref=f"heads/{pr.head.ref}")
