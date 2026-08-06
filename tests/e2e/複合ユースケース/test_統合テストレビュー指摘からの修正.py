"""「統合テストレビュー指摘からの修正」の E2E テスト。

UC は単一 UC 統合テスト（story レベル）で代表して書かれているが、読み替え先の
複合 UC 統合テスト（epic レベル）も別エージェントの実体なので、両レベルとも実行する。
"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, comments_from, issue, label_names
from tests.e2e.実装対象 import add_worktree, branch_sha
from tests.e2e.統合テスト import (
    COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE,
    COMPLEX_TESTER_DONE_REPORT,
    E2E_TEST_PY_MISSING_ERROR_CASE,
    EPIC_PR_BODY_WITH_TABLE,
    STORY_PR_BODY_WITH_TABLE,
    TESTER_DONE_REPORT,
    complex_result_rows,
    epic_branch_files,
    result_rows,
    setup_epic,
    setup_story,
    story_branch_files,
)

SINGLE = {
    "tester": "single-scenario-tester",
    "writer": "single-scenario-writer",
    "conductor": "story-conductor",
    "e2e_dir": "tests/e2e/単一ユースケース/",
    "report": TESTER_DONE_REPORT,
    "rows": result_rows,
}
COMPLEX = {
    "tester": "complex-scenario-tester",
    "writer": "complex-scenario-writer",
    "conductor": "epic-conductor",
    "e2e_dir": "tests/e2e/複合ユースケース/",
    "report": COMPLEX_TESTER_DONE_REPORT,
    "rows": complex_result_rows,
}


def _label_and_assignee_events(gh_live, owner, repo, number):
    """PR のラベル付与・assignee 設定イベントを返す。"""
    events = gh_live.rest.issues.list_events_for_timeline(
        owner=owner, repo=repo, issue_number=number, per_page=100
    ).parsed_data
    labeled = [e for e in events if getattr(e, "event", "") == "labeled"]
    assigned = [e for e in events if getattr(e, "event", "") == "assigned"]
    return labeled, assigned


def _wait_converged(gh_live, owner, repo, pr_number, parent_number, branch, wait_until, level):
    """指摘 → 修正 → 再レビューの収束（親 conductor への全 pass 完了報告）を待つ。"""

    def _check():
        if f"確認:{level['writer']}" in label_names(issue(gh_live, owner, repo, pr_number)):
            return None
        parent_now = issue(gh_live, owner, repo, parent_number)
        if f"確認:{level['conductor']}" not in label_names(parent_now):
            return None
        reports = comments_from(gh_live, owner, repo, parent_number, level["writer"])
        if not reports:
            return None
        return reports[-1], branch_sha(gh_live, owner, repo, branch)

    return wait_until(_check, timeout_sec=3600, message="指摘 → 修正 → 再レビューの収束（全 pass 完了報告）")


def _assert_converged(gh_live, owner, repo, pr_number, seed_sha, report, result, level) -> None:
    """指摘の投稿・スレッドの往復・修正 commit・完了報告・ユーザー操作なしを検証する。"""
    completion, converged_sha = result

    # 検証: インライン指摘が投稿されている
    review_comments = gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=pr_number
    ).parsed_data
    assert review_comments, "インライン指摘が投稿されていない（指摘なしで通過した可能性）"

    # 検証: 完了報告スレッドに 指揮役の対応依頼 → tester の修正報告 の順で往復が残り Resolve 済み
    thread = next(
        (c for c in comments(gh_live, owner, repo, pr_number) if c.node_id == report.node_id), None
    )
    assert thread is not None, "tester のテスト実装完了報告コメントが見つからない"
    body = thread.body or ""
    assert f"> from: @{level['writer']}" in body, "スレッドに指揮役の対応依頼が返信追記されていない"
    assert f"> from: @{level['tester']}" in body.split(f"> from: @{level['writer']}", 1)[1], (
        "スレッドに tester の修正報告がない"
    )
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    # 検証: E2E テストの修正 commit が積まれている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{converged_sha}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert [f for f in changed if f.startswith(level["e2e_dir"])], (
        f"テスト修正の commit が積まれていない: {changed}"
    )

    # 検証: 再レビューで writer が実行し、テスト結果表が全て記入されている
    pr_body = (issue(gh_live, owner, repo, pr_number).body or "").replace("\r\n", "\n")
    rows = level["rows"](pr_body)
    assert rows, "テスト結果表の行がない"
    for row in rows:
        assert "✅" in row, f"再レビュー後の結果列が ✅ で埋まっていない: {row}"

    # 検証: 完了報告が conductor 宛で未解決のまま親 Issue に投稿されている
    assert f"> to: @{level['conductor']}" in (completion.body or ""), "完了報告の宛先が conductor でない"
    assert not server._is_minimized(completion.node_id), "完了報告が Resolve されている（受領は conductor）"

    # 検証: ループ中にユーザー操作を求めていない
    labeled, assigned = _label_and_assignee_events(gh_live, owner, repo, pr_number)
    assert not [e for e in labeled if getattr(e.label, "name", "") == "議論中"], "議論中 が付与された"
    assert not assigned, "assignee が設定された（ユーザー操作を求めている）"


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
        files=story_branch_files(e2e_test=E2E_TEST_PY_MISSING_ERROR_CASE), artifact="test",
    )
    add_worktree(sandbox["local_path"], ctx["story_branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["story_branch"])

    # 準備: tester のテスト実装完了報告 → 確認ラベル付与（レビューの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=SINGLE["report"]
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=[f"確認:{SINGLE['writer']}"]
    )

    # 実行・検証
    result = _wait_converged(
        gh_live, owner, repo, ctx["pr"].number, ctx["story"].number, ctx["story_branch"],
        wait_until, SINGLE,
    )
    _assert_converged(gh_live, owner, repo, ctx["pr"].number, seed_sha, report, result, SINGLE)


def test_normal_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, commit_file, wait_until, sandbox,
):
    """統合テストレビュー指摘 → tester 修正 → 再レビューの収束を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 異常シナリオのケースが欠落した E2E テストを積む（指揮役の指摘を誘発）
    ctx = setup_epic(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory, commit_file,
        pr_body=EPIC_PR_BODY_WITH_TABLE,
        files=epic_branch_files(complex_e2e_test=COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE), artifact="test",
    )
    add_worktree(sandbox["local_path"], ctx["epic_branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["epic_branch"])

    # 準備: tester のテスト実装完了報告 → 確認ラベル付与（レビューの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=COMPLEX["report"]
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=[f"確認:{COMPLEX['writer']}"]
    )

    # 実行・検証
    result = _wait_converged(
        gh_live, owner, repo, ctx["pr"].number, ctx["epic"].number, ctx["epic_branch"],
        wait_until, COMPLEX,
    )
    _assert_converged(gh_live, owner, repo, ctx["pr"].number, seed_sha, report, result, COMPLEX)
