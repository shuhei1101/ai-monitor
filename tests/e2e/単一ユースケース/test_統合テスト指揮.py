"""「統合テスト指揮」の E2E テスト。

UC は単一 UC（story レベル）で代表して書かれているが、読み替え先の複合 UC（epic レベル）も
別エージェントの実体なので、両レベルとも実行する。
"""
from __future__ import annotations

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, comments_from, issue, label_names, waiting_for_user
from tests.e2e.実装対象 import SCENARIO_PATH, add_worktree, branch_sha
from tests.e2e.統合テスト import (
    COMPLEX_E2E_TEST_PATH,
    COMPLEX_E2E_TEST_PY,
    COMPLEX_E2E_TEST_PY_FOLLOWING_CONFLICT,
    COMPLEX_E2E_TEST_PY_WRONG_ASSERTION,
    COMPLEX_SCENARIO_MD_CONFLICTING,
    COMPLEX_SCENARIO_PATH,
    COMPLEX_TESTER_FAIL_REPORT,
    COMPLEX_TESTER_PASS_REPORT,
    E2E_TEST_PATH,
    E2E_TEST_PY,
    E2E_TEST_PY_FOLLOWING_CONFLICT,
    E2E_TEST_PY_WRONG_ASSERTION,
    EPIC_PR_BODY,
    EPIC_PR_BODY_ALL_PASSED,
    EPIC_PR_BODY_FAILED,
    SCENARIO_MD_CONFLICTING,
    STORY_PR_BODY,
    STORY_PR_BODY_ALL_PASSED,
    STORY_PR_BODY_FAILED,
    TESTER_FAIL_REPORT,
    TESTER_PASS_REPORT,
    epic_branch_files,
    setup_epic,
    setup_story,
    story_branch_files,
)

SINGLE = {
    "writer": "single-scenario-writer",
    "tester": "single-scenario-tester",
    "conductor": "story-conductor",
    "parent": "story",
    "test_path": E2E_TEST_PATH,
}
COMPLEX = {
    "writer": "complex-scenario-writer",
    "tester": "complex-scenario-tester",
    "conductor": "epic-conductor",
    "parent": "epic",
    "test_path": COMPLEX_E2E_TEST_PATH,
}

# シナリオ側 / テストコード側の fail を仕込んだときの tester 失敗報告
SCENARIO_FAIL_REPORT = """> from: @{tester}
> to: @{writer}

テスト結果表の全行を実行しました。1 件 fail です。

| ケース | 結果 |
| --- | --- |
| `test_normal_when_タイトルが空` | ❌ |

失敗内容: シナリオ設計書の `## 正常シナリオ（タイトルが空）` に沿って
「タイトルが空でも保存される」ことを検証しましたが、`ValidationError` が送出されました。
"""

TESTCODE_FAIL_REPORT = """> from: @{tester}
> to: @{writer}

テスト結果表の全行を実行しました。1 件 fail です。

| ケース | 結果 |
| --- | --- |
| `test_normal` | ❌ |

失敗内容: 本文を `新本文` に更新した直後に `旧本文` であることを検証しており、
`AssertionError: '新本文' != '旧本文'` になります。
"""


def repo_ctx_args(gh_live, repo_ctx):
    """`gh_live, owner, repo` の並びに展開する。"""
    owner, repo = repo_ctx
    return gh_live, owner, repo


def _setup(gh_live, owner, repo, level, factories, *, pr_body, files):
    """レベルに応じた統合テスト待機中の PR 一式を用意する。"""
    if level is SINGLE:
        ctx = setup_story(
            gh_live, owner, repo,
            factories["epic_issue_factory"], factories["epic_pr_factory"],
            factories["draft_pr_factory"], factories["story_issue_factory"], factories["commit_file"],
            pr_body=pr_body, files=files,
        )
        ctx["branch"] = ctx["story_branch"]
        ctx["parent_number"] = ctx["story"].number
        return ctx
    ctx = setup_epic(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["commit_file"],
        pr_body=pr_body, files=files,
    )
    ctx["branch"] = ctx["epic_branch"]
    ctx["parent_number"] = ctx["epic"].number
    return ctx


SCENARIO_DONE_REPORT = """> from: @{writer}
> to: @{login}

ユースケースシナリオの設計が完了し、ユーザー確認を経て確定しました。

| ファイル | 内容 |
| --- | --- |
| `設計図/シナリオ/` 配下 | 対象シナリオを作成し、索引にも行を追加 |
"""


def _seed_finished_scenario_design(gh_live, owner, repo, pr_number, level):
    """シナリオ設計が済んだ状態（Resolve 済みの自身コメントあり）を再現する。

    フェーズ索引では `シナリオ作成（初回）` が「自身の投稿コメントが Resolved 込みで 0 件」で
    マッチするため、統合テスト系のフェーズを起動するには過去の自分コメントが要る。
    """
    login = gh_live.rest.users.get_authenticated().parsed_data.login
    posted = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number,
        body=SCENARIO_DONE_REPORT.format(writer=level["writer"], login=login),
    ).parsed_data
    server._minimize_comment(posted.node_id)
    return posted


def _start(gh_live, owner, repo, pr_number, level, *, report: str | None = None):
    """指揮役の起動トリガー（必要なら tester の報告）を仕込む。"""
    posted = None
    if report is not None:
        posted = gh_live.rest.issues.create_comment(
            owner=owner, repo=repo, issue_number=pr_number, body=report
        ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=[f"確認:{level['writer']}"]
    )
    return posted


def _wait_assigned_to_tester(gh_live, owner, repo, pr_number, level, wait_until, *, message):
    """指揮役から tester への引き渡し（確認ラベルの入れ替え）を待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, pr_number)
        names = label_names(data)
        if f"確認:{level['tester']}" not in names or f"確認:{level['writer']}" in names:
            return None
        return data

    return wait_until(_done, timeout_sec=2400, message=message)


def _wait_reported_to_conductor(gh_live, owner, repo, pr_number, parent_number, level, wait_until, *, message):
    """指揮役から親 Issue の conductor への報告を待つ。"""

    def _done():
        pr_now = issue(gh_live, owner, repo, pr_number)
        if f"確認:{level['writer']}" in label_names(pr_now):
            return None
        parent_now = issue(gh_live, owner, repo, parent_number)
        if f"確認:{level['conductor']}" not in label_names(parent_now):
            return None
        reports = comments_from(gh_live, owner, repo, parent_number, level["writer"])
        return (pr_now, reports[-1]) if reports else None

    return wait_until(_done, timeout_sec=2400, message=message)


def _run_implement_start(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """正常シナリオ（テスト実装の起動）を実行して検証する。"""
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        pr_body=STORY_PR_BODY if level is SINGLE else EPIC_PR_BODY,
        files=story_branch_files() if level is SINGLE else epic_branch_files(),
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    done = _seed_finished_scenario_design(gh_live, owner, repo, ctx["pr"].number, level)
    _start(gh_live, owner, repo, ctx["pr"].number, level)

    data = _wait_assigned_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until, message="テスト実装タスクの割り当て",
    )

    # 検証: 実行指示コメントなしで tester へ割り当てられている
    posted = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, level["writer"])
        if c.node_id != done.node_id
    ]
    assert not posted, "テスト実装の起動で指揮役のコメントが投稿されている（実行指示は実装後）"
    assert "議論中" not in label_names(data), "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"


def _run_all_passed(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """正常シナリオ（全 pass の完了報告）を実行して検証する。"""
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        pr_body=STORY_PR_BODY_ALL_PASSED if level is SINGLE else EPIC_PR_BODY_ALL_PASSED,
        files=(
            story_branch_files(e2e_test=E2E_TEST_PY) if level is SINGLE
            else epic_branch_files(complex_e2e_test=COMPLEX_E2E_TEST_PY)
        ),
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    report = _start(
        gh_live, owner, repo, ctx["pr"].number, level,
        report=TESTER_PASS_REPORT if level is SINGLE else COMPLEX_TESTER_PASS_REPORT,
    )

    _, completion = _wait_reported_to_conductor(
        gh_live, owner, repo, ctx["pr"].number, ctx["parent_number"], level, wait_until,
        message="全 pass の完了報告",
    )

    # 検証: 完了報告が conductor 宛で未解決、tester の報告は Resolve 済み
    assert f"> to: @{level['conductor']}" in (completion.body or ""), "完了報告の宛先が conductor でない"
    assert not server._is_minimized(completion.node_id), "完了報告が Resolve されている（受領は conductor）"
    assert server._is_minimized(report.node_id), "tester の完了報告が未 Resolve"


def _run_retest(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """正常シナリオ（再テストの実行指示）を実行して検証する。"""
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        pr_body=STORY_PR_BODY_FAILED if level is SINGLE else EPIC_PR_BODY_FAILED,
        files=(
            story_branch_files(e2e_test=E2E_TEST_PY) if level is SINGLE
            else epic_branch_files(complex_e2e_test=COMPLEX_E2E_TEST_PY)
        ),
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    done = _seed_finished_scenario_design(gh_live, owner, repo, ctx["pr"].number, level)
    _start(gh_live, owner, repo, ctx["pr"].number, level)

    _wait_assigned_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until, message="再テストの実行指示",
    )

    # 検証: 実行指示コメントが tester 宛で未解決のまま投稿されている
    instructions = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, level["writer"])
        if c.node_id != done.node_id
    ]
    assert instructions, "再テストの実行指示コメントが投稿されていない"
    assert f"> to: @{level['tester']}" in (instructions[-1].body or ""), "実行指示の宛先が tester でない"
    assert not server._is_minimized(instructions[-1].node_id), "実行指示が Resolve されている"


def _run_fail_impl(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """異常シナリオ（fail・実装側の問題）を実行して検証する。"""
    from tests.e2e.統合テスト import BUGGY_SERVICE_PY

    ctx = _setup(
        gh_live, owner, repo, level, factories,
        pr_body=STORY_PR_BODY_FAILED if level is SINGLE else EPIC_PR_BODY_FAILED,
        files=(
            story_branch_files(service=BUGGY_SERVICE_PY, e2e_test=E2E_TEST_PY) if level is SINGLE
            else epic_branch_files(service=BUGGY_SERVICE_PY, complex_e2e_test=COMPLEX_E2E_TEST_PY)
        ),
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["branch"])
    report = _start(
        gh_live, owner, repo, ctx["pr"].number, level,
        report=TESTER_FAIL_REPORT if level is SINGLE else COMPLEX_TESTER_FAIL_REPORT,
    )

    _, failure = _wait_reported_to_conductor(
        gh_live, owner, repo, ctx["pr"].number, ctx["parent_number"], level, wait_until,
        message="実装側の問題としての失敗報告",
    )

    # 検証: 失敗報告が conductor 宛で未解決、tester の報告スレッドにトリアージ結果が残り Resolve 済み
    assert f"> to: @{level['conductor']}" in (failure.body or ""), "失敗報告の宛先が conductor でない"
    assert not server._is_minimized(failure.node_id), "失敗報告が Resolve されている（受領は conductor）"
    thread = next(
        c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id
    )
    assert f"> from: @{level['writer']}" in (thread.body or ""), "トリアージ結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "tester の失敗報告が未 Resolve"

    # 検証: シナリオ設計書・実装コードを直していない（差し戻し先は conductor）
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert not [f for f in changed if f.startswith("src/")], f"実装コードが変更されている: {changed}"


def _run_fail_scenario(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """異常シナリオ（fail・シナリオ側の問題）を実行して検証する。"""
    # 自分が担当するシナリオ設計書をユースケース要件と矛盾させる（実装は要件どおり）
    if level is SINGLE:
        files = story_branch_files(e2e_test=E2E_TEST_PY_FOLLOWING_CONFLICT)
        files = {**files, SCENARIO_PATH: SCENARIO_MD_CONFLICTING}
    else:
        files = epic_branch_files(complex_e2e_test=COMPLEX_E2E_TEST_PY_FOLLOWING_CONFLICT)
        files = {**files, COMPLEX_SCENARIO_PATH: COMPLEX_SCENARIO_MD_CONFLICTING}
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        pr_body=STORY_PR_BODY_FAILED if level is SINGLE else EPIC_PR_BODY_FAILED,
        files=files,
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["branch"])
    report = _start(
        gh_live, owner, repo, ctx["pr"].number, level,
        report=SCENARIO_FAIL_REPORT.format(tester=level["tester"], writer=level["writer"]),
    )

    # 実行: シナリオ修正の確認依頼（議論中 + assignee）を待つ
    def _fix_proposed():
        data = issue(gh_live, owner, repo, ctx["pr"].number)
        return data if waiting_for_user(data) else None

    data = wait_until(
        _fix_proposed, timeout_sec=2400, message="シナリオ修正の確認依頼（議論中 + assignee）"
    )

    # 検証: シナリオ設計書の修正 commit が積まれている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert [f for f in changed if f.startswith("docs/wiki/設計図/シナリオ/")], (
        f"シナリオ設計書の修正 commit が積まれていない: {changed}"
    )

    # 準備: ユーザー承認（修正の確定）
    try:
        gh_live.rest.issues.remove_label(
            owner=owner, repo=repo, issue_number=ctx["pr"].number, name="議論中"
        )
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=ctx["pr"].number, assignees=[assignee.login]
        )

    _wait_assigned_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until, message="修正 + 再実行の再開指示",
    )

    # 検証: 失敗報告スレッドに再開指示が返信追記され、未解決のまま残っている
    thread = next(
        c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id
    )
    assert f"> to: @{level['tester']}" in (thread.body or ""), "再開指示が返信追記されていない"
    assert not server._is_minimized(report.node_id), (
        "失敗報告スレッドが Resolve されている（Resolve は tester）"
    )


def _run_fail_testcode(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """異常シナリオ（fail・テストコード側の問題）を実行して検証する。"""
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        pr_body=STORY_PR_BODY_FAILED if level is SINGLE else EPIC_PR_BODY_FAILED,
        files=(
            story_branch_files(e2e_test=E2E_TEST_PY_WRONG_ASSERTION) if level is SINGLE
            else epic_branch_files(complex_e2e_test=COMPLEX_E2E_TEST_PY_WRONG_ASSERTION)
        ),
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["branch"])
    report = _start(
        gh_live, owner, repo, ctx["pr"].number, level,
        report=TESTCODE_FAIL_REPORT.format(tester=level["tester"], writer=level["writer"]),
    )

    _wait_assigned_to_tester(
        gh_live, owner, repo, ctx["pr"].number, level, wait_until, message="テストコード修正の再開指示",
    )

    # 検証: 失敗報告スレッドに指摘 + 再開指示が返信追記され、未解決のまま残っている
    thread = next(
        c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id
    )
    assert f"> to: @{level['tester']}" in (thread.body or ""), "再開指示が返信追記されていない"
    assert not server._is_minimized(report.node_id), (
        "失敗報告スレッドが Resolve されている（Resolve は tester）"
    )

    # 検証: シナリオ設計書・実装コードへの変更が発生していない
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert not [f for f in changed if f.startswith("src/")], f"実装コードが変更されている: {changed}"
    assert not [f for f in changed if f.startswith("docs/wiki/設計図/シナリオ/")], (
        f"シナリオ設計書が変更されている: {changed}"
    )


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file):
    """レベル別のセットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "commit_file": commit_file,
    }


def test_normal_implement_start_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """テスト結果表が未記入のときのテスト実装タスクの割り当てを確認する（正常系・テスト実装の起動）。"""
    _run_implement_start(
        *repo_ctx_args(gh_live, repo_ctx), SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_implement_start_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """テスト結果表が未記入のときのテスト実装タスクの割り当てを確認する（正常系・テスト実装の起動）。"""
    _run_implement_start(
        *repo_ctx_args(gh_live, repo_ctx), COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_all_passed_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """全 pass の結果判定と conductor への完了報告を確認する（正常系・全 pass の完了報告）。"""
    _run_all_passed(
        *repo_ctx_args(gh_live, repo_ctx), SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_all_passed_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """全 pass の結果判定と conductor への完了報告を確認する（正常系・全 pass の完了報告）。"""
    _run_all_passed(
        *repo_ctx_args(gh_live, repo_ctx), COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_retest_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """fail 記録済みの表からの再テスト指示を確認する（正常系・再テストの実行指示）。"""
    _run_retest(
        *repo_ctx_args(gh_live, repo_ctx), SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_retest_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """fail 記録済みの表からの再テスト指示を確認する（正常系・再テストの実行指示）。"""
    _run_retest(
        *repo_ctx_args(gh_live, repo_ctx), COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_fail_impl_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """実装側の問題としてのトリアージと conductor への失敗報告を確認する（異常系・fail・実装側の問題）。"""
    _run_fail_impl(
        *repo_ctx_args(gh_live, repo_ctx), SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_fail_impl_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """実装側の問題としてのトリアージと conductor への失敗報告を確認する（異常系・fail・実装側の問題）。"""
    _run_fail_impl(
        *repo_ctx_args(gh_live, repo_ctx), COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_fail_scenario_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ側の問題としての設計書修正と再開指示を確認する（異常系・fail・シナリオ側の問題）。"""
    _run_fail_scenario(
        *repo_ctx_args(gh_live, repo_ctx), SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_fail_scenario_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ側の問題としての設計書修正と再開指示を確認する（異常系・fail・シナリオ側の問題）。"""
    _run_fail_scenario(
        *repo_ctx_args(gh_live, repo_ctx), COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_fail_testcode_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """テストコード側の問題としての指摘と再開指示を確認する（異常系・fail・テストコード側の問題）。"""
    _run_fail_testcode(
        *repo_ctx_args(gh_live, repo_ctx), SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_error_fail_testcode_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """テストコード側の問題としての指摘と再開指示を確認する（異常系・fail・テストコード側の問題）。"""
    _run_fail_testcode(
        *repo_ctx_args(gh_live, repo_ctx), COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )
