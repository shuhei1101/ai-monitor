"""「統合テストレビュー」の E2E テスト。

UC は単一 UC（story レベル）で代表して書かれているが、読み替え先の複合 UC（epic レベル）も
別エージェントの実体なので、両レベルとも実行する。
"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import (
    comments,
    comments_from,
    issue,
    label_names,
    unresolved_review_threads,
)
from tests.e2e.実装対象 import add_worktree
from tests.e2e.統合テスト import (
    COMPLEX_E2E_TEST_PY,
    COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE,
    COMPLEX_TESTER_DONE_REPORT,
    E2E_TEST_PY,
    E2E_TEST_PY_MISSING_ERROR_CASE,
    EPIC_PR_BODY_WITH_TABLE,
    STORY_PR_BODY_WITH_TABLE,
    TESTER_DONE_REPORT,
    epic_branch_files,
    setup_epic,
    setup_story,
    story_branch_files,
)

SINGLE = {"writer": "single-scenario-writer", "tester": "single-scenario-tester"}
COMPLEX = {"writer": "complex-scenario-writer", "tester": "complex-scenario-tester"}


def _setup_single(gh_live, owner, repo, factories, *, e2e_test):
    """story レベルのテスト実装完了状態を用意する。"""
    ctx = setup_story(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["draft_pr_factory"],
        factories["story_issue_factory"], factories["commit_file"],
        pr_body=STORY_PR_BODY_WITH_TABLE, files=story_branch_files(e2e_test=e2e_test),
    )
    ctx["branch"] = ctx["story_branch"]
    return ctx


def _setup_complex(gh_live, owner, repo, factories, *, e2e_test):
    """epic レベルのテスト実装完了状態を用意する。"""
    ctx = setup_epic(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["commit_file"],
        pr_body=EPIC_PR_BODY_WITH_TABLE, files=epic_branch_files(complex_e2e_test=e2e_test),
    )
    ctx["branch"] = ctx["epic_branch"]
    return ctx


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file):
    """レベル別のセットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "commit_file": commit_file,
    }


def _start(gh_live, owner, repo, pr_number, level, report_body):
    """tester のテスト実装完了報告 → 確認ラベル付与（レビューの起動トリガー）。"""
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number, body=report_body
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=[f"確認:{level['writer']}"]
    )
    return report


def _wait_handed_to_tester(gh_live, owner, repo, pr_number, level, wait_until, *, message):
    """レビュー後の tester への引き渡し（確認ラベルの入れ替え）を待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, pr_number)
        names = label_names(data)
        if f"確認:{level['tester']}" not in names or f"確認:{level['writer']}" in names:
            return None
        return data

    return wait_until(_done, timeout_sec=2400, message=message)


def _run_normal(gh_live, owner, repo, level, setup, factories, wait_until, sandbox, *, e2e_test, report_body):
    """正常シナリオ（指摘なし）を実行して検証する。"""
    ctx = setup(gh_live, owner, repo, factories, e2e_test=e2e_test)
    add_worktree(sandbox["local_path"], ctx["branch"])
    report = _start(gh_live, owner, repo, ctx["pr"].number, level, report_body)

    _wait_handed_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until, message="レビュー通過と実行指示",
    )

    # 検証: 完了報告スレッドにレビュー結果が返信追記され、Resolve 済み
    thread = next(
        c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id
    )
    assert f"> from: @{level['writer']}" in (thread.body or ""), "レビュー結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    # 検証: 未解決のインライン指摘スレッドが残っていない
    unresolved = unresolved_review_threads(gh_live, owner, repo, ctx["pr"].number)
    assert not unresolved, f"未解決のインライン指摘スレッドが残っている: {unresolved}"

    # 検証: 実行指示コメントが tester 宛で未解決のまま投稿されている
    instructions = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, level["writer"])
        if c.node_id != report.node_id
    ]
    assert instructions, "実行指示コメントが投稿されていない"
    assert f"> to: @{level['tester']}" in (instructions[-1].body or ""), "実行指示の宛先が tester でない"
    assert not server._is_minimized(instructions[-1].node_id), "実行指示が Resolve されている"


def _run_pointed_out(
    gh_live, owner, repo, level, setup, factories, wait_until, sandbox, *, e2e_test, report_body
):
    """異常シナリオ（テストへの指摘あり）を実行して検証する。"""
    ctx = setup(gh_live, owner, repo, factories, e2e_test=e2e_test)
    add_worktree(sandbox["local_path"], ctx["branch"])
    report = _start(gh_live, owner, repo, ctx["pr"].number, level, report_body)

    _wait_handed_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until, message="指摘の投稿と tester への差し戻し",
    )

    # 検証: インライン指摘が投稿されている
    assert gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=ctx["pr"].number
    ).parsed_data, "インライン指摘が投稿されていない（指摘なしで通過した可能性）"

    # 検証: 完了報告スレッドに対応依頼が返信追記され、未解決のまま残っている
    thread = next(
        c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id
    )
    assert f"> to: @{level['tester']}" in (thread.body or ""), "対応依頼が返信追記されていない"
    assert not server._is_minimized(report.node_id), (
        "完了報告スレッドが Resolve されている（修正確定まで同スレッドで往復する）"
    )


def test_normal_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ設計書との照合で指摘なし → 実行指示までを確認する（正常系）。"""
    owner, repo = repo_ctx
    _run_normal(
        gh_live, owner, repo, SINGLE, _setup_single,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox, e2e_test=E2E_TEST_PY, report_body=TESTER_DONE_REPORT,
    )


def test_normal_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ設計書との照合で指摘なし → 実行指示までを確認する（正常系）。"""
    owner, repo = repo_ctx
    _run_normal(
        gh_live, owner, repo, COMPLEX, _setup_complex,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox, e2e_test=COMPLEX_E2E_TEST_PY, report_body=COMPLEX_TESTER_DONE_REPORT,
    )


def test_error_pointed_out_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """異常シナリオのケース欠落を指摘して tester へ差し戻すことを確認する（異常系・テストへの指摘あり）。"""
    owner, repo = repo_ctx
    _run_pointed_out(
        gh_live, owner, repo, SINGLE, _setup_single,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
        e2e_test=E2E_TEST_PY_MISSING_ERROR_CASE, report_body=TESTER_DONE_REPORT,
    )


def test_error_pointed_out_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """異常シナリオのケース欠落を指摘して tester へ差し戻すことを確認する（異常系・テストへの指摘あり）。"""
    owner, repo = repo_ctx
    _run_pointed_out(
        gh_live, owner, repo, COMPLEX, _setup_complex,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
        e2e_test=COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE, report_body=COMPLEX_TESTER_DONE_REPORT,
    )
