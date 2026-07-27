"""「統合テストレビュー指摘からの修正」の E2E テスト。

UC は単一 UC 統合テスト（story レベル）で代表して書かれているが、読み替え先の
複合 UC 統合テスト（epic レベル）も別エージェントの実体なので、両レベルとも実行する。
"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.統合テスト import (
    COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE,
    COMPLEX_TESTER_DONE_REPORT,
    E2E_TEST_PY_MISSING_ERROR_CASE,
    EPIC_PR_BODY_WITH_TABLE,
    STORY_PR_BODY_WITH_TABLE,
    TESTER_DONE_REPORT,
    epic_branch_files,
    setup_epic,
    setup_story,
    story_branch_files,
)
from tests.e2e.実装対象 import add_worktree, branch_sha

SINGLE = {
    "tester": "single-scenario-tester",
    "writer": "single-scenario-writer",
    "e2e_dir": "tests/e2e/単一ユースケース/",
}
COMPLEX = {
    "tester": "complex-scenario-tester",
    "writer": "complex-scenario-writer",
    "e2e_dir": "tests/e2e/複合ユースケース/",
}


def _label_and_assignee_events(gh_live, owner, repo, number):
    """PR のラベル付与・assignee 設定イベントを返す。"""
    events = gh_live.rest.issues.list_events_for_timeline(
        owner=owner, repo=repo, issue_number=number, per_page=100
    ).parsed_data
    labeled = [e for e in events if getattr(e, "event", "") == "labeled"]
    assigned = [e for e in events if getattr(e, "event", "") == "assigned"]
    return labeled, assigned


def _wait_converged(gh_live, owner, repo, pr_number, branch, wait_until, level):
    """指摘 → 修正 → 再レビューの収束（実行指示の投稿）を待つ。"""

    def _check():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=pr_number).parsed_data
        labels = {label.name for label in data.labels}
        if f"確認:{level['tester']}" not in labels:
            return None
        comments = gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=pr_number
        ).parsed_data
        # 実行指示は指揮役が新規コメントとして投稿する（指摘の対応依頼は完了報告スレッドへの返信）
        instructions = [
            c for c in comments
            if (c.body or "").lstrip().startswith(f"> from: @{level['writer']}")
        ]
        if not instructions:
            return None
        return data, comments, instructions[-1], branch_sha(gh_live, owner, repo, branch)

    return wait_until(_check, timeout_sec=3600, message="指摘 → 修正 → 再レビューの収束（実行指示の投稿）")


def _assert_converged(gh_live, owner, repo, pr_number, branch, seed_sha, report, result, level) -> None:
    """指摘の投稿・スレッドの往復・修正 commit・実行指示・ユーザー操作なしを検証する。"""
    data, comments, instruction, converged_sha = result

    review_comments = gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=pr_number
    ).parsed_data
    assert review_comments, "インライン指摘が投稿されていない（指摘なしで通過した可能性）"

    thread = next((c for c in comments if c.node_id == report.node_id), None)
    assert thread is not None, "tester のテスト実装完了報告コメントが見つからない"
    body = thread.body or ""
    assert f"> from: @{level['writer']}" in body, "スレッドに指揮役の対応依頼が返信追記されていない"
    assert f"> from: @{level['tester']}" in body.split(f"> from: @{level['writer']}", 1)[1], (
        "スレッドに tester の修正報告がない"
    )
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{converged_sha}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert [f for f in changed if f.startswith(level["e2e_dir"])], (
        f"テスト修正の commit が積まれていない: {changed}"
    )

    assert f"> to: @{level['tester']}" in (instruction.body or ""), "実行指示の宛先が tester になっていない"
    assert not server._is_minimized(instruction.node_id), "実行指示が Resolve されている（受領は tester が行う）"

    labeled, assigned = _label_and_assignee_events(gh_live, owner, repo, pr_number)
    assert not [e for e in labeled if getattr(e.label, "name", "") == "議論中"], "議論中 が付与された"
    assert not assigned, "assignee が設定された（ユーザー操作を求めている）"
    assert data is not None


def test_normal_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """統合テストレビュー指摘 → tester 修正 → 再レビューの収束を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 異常シナリオのケースが欠落した E2E テストを積む（指揮役の指摘を誘発）
    ctx = setup_story(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file,
        pr_body=STORY_PR_BODY_WITH_TABLE,
        files=story_branch_files(e2e_test=E2E_TEST_PY_MISSING_ERROR_CASE),
    )
    add_worktree(sandbox["local_path"], ctx["story_branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["story_branch"])

    # 準備: tester のテスト実装完了報告 → 確認ラベル付与（レビューの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=TESTER_DONE_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=[f"確認:{SINGLE['writer']}"]
    )

    # 実行・検証
    result = _wait_converged(
        gh_live, owner, repo, ctx["pr"].number, ctx["story_branch"], wait_until, SINGLE
    )
    _assert_converged(
        gh_live, owner, repo, ctx["pr"].number, ctx["story_branch"], seed_sha, report, result, SINGLE
    )


def test_normal_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, commit_file, wait_until, sandbox,
):
    """統合テストレビュー指摘 → tester 修正 → 再レビューの収束を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 異常シナリオのケースが欠落した E2E テストを積む（指揮役の指摘を誘発）
    ctx = setup_epic(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory, commit_file,
        pr_body=EPIC_PR_BODY_WITH_TABLE,
        files=epic_branch_files(complex_e2e_test=COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE),
    )
    add_worktree(sandbox["local_path"], ctx["epic_branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["epic_branch"])

    # 準備: tester のテスト実装完了報告 → 確認ラベル付与（レビューの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=COMPLEX_TESTER_DONE_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=[f"確認:{COMPLEX['writer']}"]
    )

    # 実行・検証
    result = _wait_converged(
        gh_live, owner, repo, ctx["pr"].number, ctx["epic_branch"], wait_until, COMPLEX
    )
    _assert_converged(
        gh_live, owner, repo, ctx["pr"].number, ctx["epic_branch"], seed_sha, report, result, COMPLEX
    )
