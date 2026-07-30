"""「統合テストレビュー」の E2E テスト。

UC は単一 UC（story レベル）で代表して書かれているが、読み替え先の複合 UC（epic レベル）も
別エージェントの実体なので、両レベルとも実行する。
"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import (
    approve,
    comments,
    comments_from,
    issue,
    label_names,
    unresolved_review_threads,
    waiting_for_user,
)
from tests.e2e.実装対象 import SCENARIO_PATH, add_worktree, branch_sha
from tests.e2e.統合テスト import (
    BUGGY_SERVICE_PY,
    COMPLEX_E2E_TEST_PY,
    COMPLEX_E2E_TEST_PY_FOLLOWING_CONFLICT,
    COMPLEX_E2E_TEST_PY_MISSING_ARG,
    COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE,
    COMPLEX_SCENARIO_MD_CONFLICTING,
    COMPLEX_SCENARIO_PATH,
    COMPLEX_TESTER_DONE_REPORT,
    E2E_TEST_PY,
    E2E_TEST_PY_FOLLOWING_CONFLICT,
    E2E_TEST_PY_MISSING_ARG,
    E2E_TEST_PY_MISSING_ERROR_CASE,
    EPIC_PR_BODY_WITH_TABLE,
    SCENARIO_MD_CONFLICTING,
    SERVICE_PY,
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
    "writer": "single-scenario-writer",
    "tester": "single-scenario-tester",
    "conductor": "story-conductor",
    "report": TESTER_DONE_REPORT,
    "e2e_test": E2E_TEST_PY,
    "missing_error_case": E2E_TEST_PY_MISSING_ERROR_CASE,
    "missing_arg": E2E_TEST_PY_MISSING_ARG,
    "following_conflict": E2E_TEST_PY_FOLLOWING_CONFLICT,
    "scenario_path": SCENARIO_PATH,
    "conflicting_scenario": SCENARIO_MD_CONFLICTING,
    "rows": result_rows,
}
COMPLEX = {
    "writer": "complex-scenario-writer",
    "tester": "complex-scenario-tester",
    "conductor": "epic-conductor",
    "report": COMPLEX_TESTER_DONE_REPORT,
    "e2e_test": COMPLEX_E2E_TEST_PY,
    "missing_error_case": COMPLEX_E2E_TEST_PY_MISSING_ERROR_CASE,
    "missing_arg": COMPLEX_E2E_TEST_PY_MISSING_ARG,
    "following_conflict": COMPLEX_E2E_TEST_PY_FOLLOWING_CONFLICT,
    "scenario_path": COMPLEX_SCENARIO_PATH,
    "conflicting_scenario": COMPLEX_SCENARIO_MD_CONFLICTING,
    "rows": complex_result_rows,
}


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file):
    """レベル別のセットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "commit_file": commit_file,
    }


def _setup(gh_live, owner, repo, level, factories, *, e2e_test, service=SERVICE_PY, extra=None):
    """テスト実装完了直後（結果列が未記入）の PR 一式をレベル別に用意する。"""
    # story レベルは story ブランチ、epic レベルは epic ブランチへ資材を積む
    if level is SINGLE:
        files = story_branch_files(service=service, e2e_test=e2e_test)
        files = {**files, **(extra or {})}
        ctx = setup_story(
            gh_live, owner, repo,
            factories["epic_issue_factory"], factories["epic_pr_factory"],
            factories["draft_pr_factory"], factories["story_issue_factory"], factories["commit_file"],
            pr_body=STORY_PR_BODY_WITH_TABLE, files=files,
        )
        ctx["branch"] = ctx["story_branch"]
        ctx["parent_number"] = ctx["story"].number
        return ctx
    files = epic_branch_files(service=service, complex_e2e_test=e2e_test)
    files = {**files, **(extra or {})}
    ctx = setup_epic(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["commit_file"],
        pr_body=EPIC_PR_BODY_WITH_TABLE, files=files,
    )
    ctx["branch"] = ctx["epic_branch"]
    ctx["parent_number"] = ctx["epic"].number
    return ctx


def _start(gh_live, owner, repo, pr_number, level):
    """tester のテスト実装完了報告 → 確認ラベル付与（レビューの起動トリガー）。"""
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number, body=level["report"]
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=[f"確認:{level['writer']}"]
    )
    return report


def _wait_handed_to_tester(gh_live, owner, repo, pr_number, level, wait_until, *, message):
    """tester への差し戻し（確認ラベルの入れ替え）を待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, pr_number)
        names = label_names(data)
        if f"確認:{level['tester']}" not in names or f"確認:{level['writer']}" in names:
            return None
        return data

    return wait_until(_done, timeout_sec=2400, message=message)


def _wait_reported_to_conductor(gh_live, owner, repo, pr_number, parent_number, level, wait_until, *, message):
    """親 Issue の conductor への報告を待つ。"""

    def _done():
        if f"確認:{level['writer']}" in label_names(issue(gh_live, owner, repo, pr_number)):
            return None
        parent_now = issue(gh_live, owner, repo, parent_number)
        if f"確認:{level['conductor']}" not in label_names(parent_now):
            return None
        reports = comments_from(gh_live, owner, repo, parent_number, level["writer"])
        return reports[-1] if reports else None

    return wait_until(_done, timeout_sec=2400, message=message)


def _thread(gh_live, owner, repo, pr_number, report):
    """完了報告コメントの最新スナップショット（返信追記込み）を返す。"""
    return next(c for c in comments(gh_live, owner, repo, pr_number) if c.node_id == report.node_id)


def _changed_files(gh_live, owner, repo, seed_sha, branch) -> list[str]:
    """seed 以降にブランチへ積まれた変更ファイル一覧を返す。"""
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{branch}"
    ).parsed_data
    return [f.filename for f in (compare.files or [])]


def _run_all_passed(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """正常シナリオ（全 pass）を実行して検証する。"""
    # 準備: シナリオを満たす E2E テストと要件どおりの実装（実行すれば全 pass になる）
    ctx = _setup(gh_live, owner, repo, level, factories, e2e_test=level["e2e_test"])
    add_worktree(sandbox["local_path"], ctx["branch"])
    report = _start(gh_live, owner, repo, ctx["pr"].number, level)

    # 実行: 照合 → テスト実行 → 全 pass → 親への完了報告 まで進むのを待つ
    completion = _wait_reported_to_conductor(
        gh_live, owner, repo, ctx["pr"].number, ctx["parent_number"], level, wait_until,
        message="全 pass の完了報告",
    )

    # 検証: テスト結果表の結果列が全て記入されている
    body = (issue(gh_live, owner, repo, ctx["pr"].number).body or "").replace("\r\n", "\n")
    rows = level["rows"](body)
    assert rows, "テスト結果表の行がない"
    for row in rows:
        assert "✅" in row, f"結果列が ✅ で埋まっていない: {row}"

    # 検証: 完了報告スレッドにレビュー結果が返信追記され、Resolve 済み
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert f"> from: @{level['writer']}" in (thread.body or ""), "レビュー結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    # 検証: 未解決のインライン指摘スレッドが残っていない
    unresolved = unresolved_review_threads(gh_live, owner, repo, ctx["pr"].number)
    assert not unresolved, f"未解決のインライン指摘スレッドが残っている: {unresolved}"

    # 検証: 完了報告が conductor 宛で未解決のまま親 Issue に投稿されている
    assert f"> to: @{level['conductor']}" in (completion.body or ""), "完了報告の宛先が conductor でない"
    assert not server._is_minimized(completion.node_id), "完了報告が Resolve されている（受領は conductor）"


def _run_pointed_out(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """異常シナリオ（テストへの指摘あり）を実行して検証する。"""
    # 準備: 異常シナリオのケースが欠落した E2E テスト（照合レビューでの指摘を誘発）
    ctx = _setup(gh_live, owner, repo, level, factories, e2e_test=level["missing_error_case"])
    add_worktree(sandbox["local_path"], ctx["branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["branch"])
    report = _start(gh_live, owner, repo, ctx["pr"].number, level)

    # 実行: 指摘の投稿と tester への差し戻しを待つ
    _wait_handed_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until,
        message="指摘の投稿と tester への差し戻し",
    )

    # 検証: インライン指摘が投稿されている
    assert gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=ctx["pr"].number
    ).parsed_data, "インライン指摘が投稿されていない（指摘なしで通過した可能性）"

    # 検証: 完了報告スレッドに対応依頼が返信追記され、未解決のまま残っている
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert f"> to: @{level['tester']}" in (thread.body or ""), "対応依頼が返信追記されていない"
    assert not server._is_minimized(report.node_id), (
        "完了報告スレッドが Resolve されている（修正確定まで同スレッドで往復する）"
    )

    # 検証: テストを実行した記録がない（照合レビューで差し戻したため）
    body = (issue(gh_live, owner, repo, ctx["pr"].number).body or "").replace("\r\n", "\n")
    for row in level["rows"](body):
        assert "✅" not in row and "❌" not in row, f"結果列が記入されている: {row}"
    assert not _changed_files(gh_live, owner, repo, seed_sha, ctx["branch"]), (
        "照合レビューでの差し戻しなのに commit が積まれている"
    )


def _run_fail_impl(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """異常シナリオ（fail・実装側の問題）を実行して検証する。"""
    # 準備: 実装にバグを仕込む（シナリオもテストコードも正しい状態で fail する）
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        e2e_test=level["e2e_test"], service=BUGGY_SERVICE_PY,
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["branch"])
    report = _start(gh_live, owner, repo, ctx["pr"].number, level)

    # 実行: 実装側の問題としてのトリアージと親への失敗報告を待つ
    failure = _wait_reported_to_conductor(
        gh_live, owner, repo, ctx["pr"].number, ctx["parent_number"], level, wait_until,
        message="実装側の問題としての失敗報告",
    )

    # 検証: fail 結果がテスト結果表に記録されている
    body = (issue(gh_live, owner, repo, ctx["pr"].number).body or "").replace("\r\n", "\n")
    assert [row for row in level["rows"](body) if "❌" in row], "fail 結果が記録されていない"

    # 検証: 完了報告スレッドにトリアージ結果が残り Resolve 済み
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert f"> from: @{level['writer']}" in (thread.body or ""), "トリアージ結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "tester の完了報告が未 Resolve"

    # 検証: 失敗報告が conductor 宛で未解決（バグ差し戻しは conductor の担当）
    assert f"> to: @{level['conductor']}" in (failure.body or ""), "失敗報告の宛先が conductor でない"
    assert not server._is_minimized(failure.node_id), "失敗報告が Resolve されている（受領は conductor）"

    # 検証: 実装コードを直していない（差し戻し先は conductor）
    changed = _changed_files(gh_live, owner, repo, seed_sha, ctx["branch"])
    assert not [f for f in changed if f.startswith("src/")], f"実装コードが変更されている: {changed}"


def _run_fail_scenario(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """異常シナリオ（fail・シナリオ側の問題）を実行して検証する。"""
    # 準備: シナリオ設計書をユースケース要件と矛盾させ、それに忠実なテストを積む（実装は要件どおり）
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        e2e_test=level["following_conflict"],
        extra={level["scenario_path"]: level["conflicting_scenario"]},
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["branch"])
    report = _start(gh_live, owner, repo, ctx["pr"].number, level)

    # 実行: シナリオ修正の確認依頼（議論中 + assignee）を待つ
    def _fix_proposed():
        data = issue(gh_live, owner, repo, ctx["pr"].number)
        return data if waiting_for_user(data) else None

    data = wait_until(
        _fix_proposed, timeout_sec=2400, message="シナリオ修正の確認依頼（議論中 + assignee）"
    )

    # 検証: シナリオ設計書の修正 commit が積まれている
    changed = _changed_files(gh_live, owner, repo, seed_sha, ctx["branch"])
    assert [f for f in changed if f.startswith("docs/wiki/設計図/シナリオ/")], (
        f"シナリオ設計書の修正 commit が積まれていない: {changed}"
    )

    # 準備: ユーザー承認（修正の確定）
    approve(gh_live, owner, repo, ctx["pr"].number, data.assignees)

    # 実行: テスト修正の再開指示（tester への差し戻し）を待つ
    _wait_handed_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until, message="テスト修正の再開指示",
    )

    # 検証: 完了報告スレッドに再開指示が返信追記され、未解決のまま残っている
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert f"> to: @{level['tester']}" in (thread.body or ""), "再開指示が返信追記されていない"
    assert not server._is_minimized(report.node_id), (
        "完了報告スレッドが Resolve されている（Resolve は tester）"
    )


def _run_fail_testcode(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """異常シナリオ（fail・テストコード側の問題）を実行して検証する。"""
    # 準備: 期待値はシナリオどおりで実行操作だけ誤ったテストを積む（照合では見抜けず実行で落ちる）
    ctx = _setup(gh_live, owner, repo, level, factories, e2e_test=level["missing_arg"])
    add_worktree(sandbox["local_path"], ctx["branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["branch"])
    report = _start(gh_live, owner, repo, ctx["pr"].number, level)

    # 実行: テストコード修正の再開指示（tester への差し戻し）を待つ
    _wait_handed_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until,
        message="テストコード修正の再開指示",
    )

    # 検証: 完了報告スレッドに指摘 + 再開指示が返信追記され、未解決のまま残っている
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert f"> to: @{level['tester']}" in (thread.body or ""), "再開指示が返信追記されていない"
    assert not server._is_minimized(report.node_id), (
        "完了報告スレッドが Resolve されている（Resolve は tester）"
    )

    # 検証: シナリオ設計書・実装コードへの変更が発生していない
    changed = _changed_files(gh_live, owner, repo, seed_sha, ctx["branch"])
    assert not [f for f in changed if f.startswith("src/")], f"実装コードが変更されている: {changed}"
    assert not [f for f in changed if f.startswith("docs/wiki/設計図/シナリオ/")], (
        f"シナリオ設計書が変更されている: {changed}"
    )


def test_normal_when_all_passed_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """指摘なしの照合 → 実行で全 pass → conductor への完了報告を確認する（正常系・全 pass）。"""
    owner, repo = repo_ctx
    _run_all_passed(
        gh_live, owner, repo, SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_when_all_passed_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """指摘なしの照合 → 実行で全 pass → conductor への完了報告を確認する（正常系・全 pass）。"""
    owner, repo = repo_ctx
    _run_all_passed(
        gh_live, owner, repo, COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_when_pointed_out_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """異常シナリオのケース欠落を指摘して tester へ差し戻すことを確認する（異常系・テストへの指摘あり）。"""
    owner, repo = repo_ctx
    _run_pointed_out(
        gh_live, owner, repo, SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_when_pointed_out_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """異常シナリオのケース欠落を指摘して tester へ差し戻すことを確認する（異常系・テストへの指摘あり）。"""
    owner, repo = repo_ctx
    _run_pointed_out(
        gh_live, owner, repo, COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_when_fail_impl_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """実装側の問題としてのトリアージと conductor への失敗報告を確認する（異常系・fail・実装側の問題）。"""
    owner, repo = repo_ctx
    _run_fail_impl(
        gh_live, owner, repo, SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_when_fail_impl_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """実装側の問題としてのトリアージと conductor への失敗報告を確認する（異常系・fail・実装側の問題）。"""
    owner, repo = repo_ctx
    _run_fail_impl(
        gh_live, owner, repo, COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_when_fail_scenario_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ側の問題としての設計書修正と再開指示を確認する（異常系・fail・シナリオ側の問題）。"""
    owner, repo = repo_ctx
    _run_fail_scenario(
        gh_live, owner, repo, SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_when_fail_scenario_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ側の問題としての設計書修正と再開指示を確認する（異常系・fail・シナリオ側の問題）。"""
    owner, repo = repo_ctx
    _run_fail_scenario(
        gh_live, owner, repo, COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_when_fail_testcode_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """テストコード側の問題としての指摘と再開指示を確認する（異常系・fail・テストコード側の問題）。"""
    owner, repo = repo_ctx
    _run_fail_testcode(
        gh_live, owner, repo, SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_when_fail_testcode_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """テストコード側の問題としての指摘と再開指示を確認する（異常系・fail・テストコード側の問題）。"""
    owner, repo = repo_ctx
    _run_fail_testcode(
        gh_live, owner, repo, COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )
