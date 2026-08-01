"""「実装レビュー」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import (
    comments,
    comments_from,
    issue,
    label_names,
    unresolved_review_threads,
)
from tests.e2e.実装対象 import (
    DEVIATING_MODELS_PY,
    DEVIATING_SERVICE_PY,
    IMPL_CONFLICT_MODULE_MD,
    IMPLEMENTED_SERVICE_PY,
    MODELS_PY,
    MODULE_PATH,
    NO_RETURN_SERVICE_PY,
    RED_TEST_PATH,
    RED_TEST_PY,
    UNVALIDATED_SERVICE_PY,
    WRONG_EXPECTATION_TEST_PY,
    branch_sha,
    run_branch_tests,
    seed_subsystem_branch,
    setup_subsystem,
)

PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [x] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [x] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [x] `update_task` を実装
- [x] 単体テストを追加
- [ ] 単体テストを実行

## 単体テスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/tasks/test_service.py` | 全実行 | | 6 ケース |

## 結合テスト結果

なし
"""

IMPLEMENTER_REPORT = """> from: @implementer
> to: @architect

実装が完了しました。

- 消化したタスク: `update_task` の実装
- テストの実行とテスト結果表の記入は未実施（architect の領分）

| commit | 内容 |
| --- | --- |
| seed | update_task を実装 |

------
"""


def _setup(
    gh_live, owner, repo, factories, commit_file,
    *, models: str = MODELS_PY, service: str = IMPLEMENTED_SERVICE_PY,
    test_py: str = RED_TEST_PY, design_overrides: dict[str, str] | None = None,
):
    """実装完了時点（Draft のまま）の subsystem PR 一式を用意する。"""
    ctx = setup_subsystem(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["draft_pr_factory"],
        factories["story_issue_factory"], factories["subsystem_issue_factory"], commit_file,
        pr_body=PR_BODY,
    )
    seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"], design_overrides=design_overrides
    )
    commit_file(ctx["subsystem_branch"], "tests/tasks/__init__.py", "", "chore: e2e 用のテストパッケージを配置")
    commit_file(ctx["subsystem_branch"], RED_TEST_PATH, test_py, "test: 単体テストを追加")
    commit_file(ctx["subsystem_branch"], "src/tasks/models.py", models, "feat: Task を更新")
    commit_file(ctx["subsystem_branch"], "src/tasks/service.py", service, "feat: update_task を実装")
    ctx["seed_sha"] = branch_sha(gh_live, owner, repo, ctx["subsystem_branch"])
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=IMPLEMENTER_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )
    return ctx, report


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory):
    """セットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "subsystem_issue_factory": subsystem_issue_factory,
    }


def _wait_handed_to(gh_live, owner, repo, pr_number, target: str, wait_until, *, message):
    """architect から指定の担当への引き渡し（確認ラベルの入れ替え）を待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, pr_number)
        names = label_names(data)
        if f"確認:{target}" not in names or "確認:architect" in names:
            return None
        return data

    return wait_until(_done, timeout_sec=2400, message=message)


def _thread(gh_live, owner, repo, pr_number, report):
    """implementer の完了報告コメントの最新スナップショットを返す。"""
    return next(c for c in comments(gh_live, owner, repo, pr_number) if c.node_id == report.node_id)


def _changed_files(gh_live, owner, repo, seed_sha, branch) -> list[str]:
    """seed 以降にブランチへ積まれた変更ファイル一覧を返す。"""
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{branch}"
    ).parsed_data
    return [f.filename for f in (compare.files or [])]


def _result_rows(body: str) -> list[str]:
    """`## 単体テスト結果` の表のデータ行を返す。"""
    section = body.replace("\r\n", "\n").split("## 単体テスト結果", 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if line.startswith("|")][2:]


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """設計どおりの実装を指摘なしで通し subsystem-conductor へ一式完了報告することを確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx, report = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file,
    )

    data = _wait_handed_to(
        gh_live, owner, repo, ctx["pr"].number, "subsystem-conductor", wait_until,
        message="実装レビュー通過と一式完了報告",
    )

    # 検証: worktree でのテスト再実行が Green（実測）
    result = run_branch_tests(sandbox["local_path"], ctx["subsystem_branch"])
    assert result.returncode == 0, f"テストが Green でない:\n{result.stderr[-1500:]}"

    # 検証: 未解決のインライン指摘スレッドが残っていない
    unresolved = unresolved_review_threads(gh_live, owner, repo, ctx["pr"].number)
    assert not unresolved, f"未解決のインライン指摘スレッドが残っている: {unresolved}"

    # 検証: 完了報告スレッドにレビュー結果が返信追記され、Resolve 済み
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert "> from: @architect" in (thread.body or ""), "レビュー結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    # 検証: テスト結果表が全て ✅ でタスク一覧が全チェック済み
    body = (data.body or "").replace("\r\n", "\n")
    for row in _result_rows(body):
        assert "✅" in row, f"テスト結果表の結果列が ✅ で埋まっていない: {row}"
    assert "- [ ]" not in body, "タスク一覧に未チェックの行が残っている（architect がテスト実行の行を入れて全行が埋まる）"

    # 検証: PR が Ready 化されている
    pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=ctx["pr"].number).parsed_data
    assert pr_now.draft is False, "PR が Draft のまま（Green 確認後は Ready 化する）"

    # 検証: 一式完了報告が subsystem-conductor 宛で未解決のまま投稿されている
    handoffs = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, "architect")
        if c.node_id != report.node_id
    ]
    assert handoffs, "一式完了報告が投稿されていない"
    assert "> to: @subsystem-conductor" in (handoffs[-1].body or ""), "一式完了報告の宛先が違う"
    assert not server._is_minimized(handoffs[-1].node_id), "一式完了報告が Resolve されている"


def test_error_when_pointed_out(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """設計 Wiki に無い項目を指摘して implementer へ差し戻すことを確認する（異常系・実装への指摘あり）。"""
    owner, repo = repo_ctx
    ctx, report = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, models=DEVIATING_MODELS_PY, service=DEVIATING_SERVICE_PY,
    )

    data = _wait_handed_to(
        gh_live, owner, repo, ctx["pr"].number, "implementer", wait_until,
        message="指摘の投稿と implementer への差し戻し",
    )

    # 検証: インライン指摘が投稿されている
    assert gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=ctx["pr"].number
    ).parsed_data, "インライン指摘が投稿されていない（指摘なしで通過した可能性）"

    # 検証: 完了報告スレッドに対応依頼が返信追記され、未解決のまま残っている
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert "> to: @implementer" in (thread.body or ""), "対応依頼が返信追記されていない"
    assert not server._is_minimized(report.node_id), (
        "完了報告スレッドが Resolve されている（修正確定まで同スレッドで往復する）"
    )

    # 検証: タスク一覧の実装タスクは未チェックのまま
    impl_lines = [
        line for line in (data.body or "").replace("\r\n", "\n").splitlines()
        if "`update_task` を実装" in line
    ]
    assert impl_lines and impl_lines[0].strip().startswith("- [ ]"), (
        f"実装タスクがチェックされている: {impl_lines}"
    )


def test_error_when_fail_impl(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """実装側の問題としての差し戻しを確認する（異常系・fail・実装側の問題）。"""
    owner, repo = repo_ctx
    # 準備: タイトル検証を落とした実装（設計 Wiki・テストコードは正しい）
    ctx, report = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, service=UNVALIDATED_SERVICE_PY,
    )

    data = _wait_handed_to(
        gh_live, owner, repo, ctx["pr"].number, "implementer", wait_until,
        message="実装側の問題としての差し戻し",
    )

    # 検証: fail 結果がテスト結果表に記録されている
    assert [row for row in _result_rows(data.body or "") if "❌" in row], "fail 結果が記録されていない"

    # 検証: 完了報告スレッドに再修正の依頼が返信追記され、未解決のまま残っている
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert "> to: @implementer" in (thread.body or ""), "再修正の依頼が返信追記されていない"
    assert not server._is_minimized(report.node_id), "完了報告スレッドが Resolve されている"

    # 検証: architect が実装コードを変更していない（修正は implementer の担当）
    changed = _changed_files(gh_live, owner, repo, ctx["seed_sha"], ctx["subsystem_branch"])
    assert not [f for f in changed if f.startswith("src/")], f"実装コードが変更されている: {changed}"

    # 検証: PR が Draft のまま（Ready 化は Green 確認後）
    pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=ctx["pr"].number).parsed_data
    assert pr_now.draft is True, "fail なのに PR が Ready 化されている"


def test_error_when_fail_design(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """設計側の問題としての設計 Wiki 修正と再実装の依頼を確認する（異常系・fail・設計側の問題）。"""
    owner, repo = repo_ctx
    # 準備: 戻り値なしの設計とそれに忠実な実装（レビュー済みテストは戻り値を検証するので落ちる）
    ctx, report = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, service=NO_RETURN_SERVICE_PY,
        design_overrides={MODULE_PATH: IMPL_CONFLICT_MODULE_MD},
    )

    _wait_handed_to(
        gh_live, owner, repo, ctx["pr"].number, "implementer", wait_until,
        message="設計側の問題としての差し戻し",
    )

    # 検証: 設計 Wiki の修正 commit が積まれ、実装 / テストコードは変更されていない
    changed = _changed_files(gh_live, owner, repo, ctx["seed_sha"], ctx["subsystem_branch"])
    assert [f for f in changed if f.startswith("docs/wiki/設計図/")], (
        f"設計 Wiki の修正 commit が積まれていない: {changed}"
    )
    assert not [f for f in changed if f.startswith("src/") or f.startswith("tests/")], (
        f"実装 / テストコードが変更されている: {changed}"
    )

    # 検証: 完了報告スレッドに再実装の依頼が返信追記されている
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert "> to: @implementer" in (thread.body or ""), "再実装の依頼が返信追記されていない"


def test_error_when_fail_testcode(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """テストコード側の問題としての tester への差し戻しを確認する（異常系・fail・テストコード側の問題）。"""
    owner, repo = repo_ctx
    # 準備: 本文省略時の期待値を取り違えたテストコード（設計 Wiki・実装は正しい）
    ctx, report = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, test_py=WRONG_EXPECTATION_TEST_PY,
    )

    _wait_handed_to(
        gh_live, owner, repo, ctx["pr"].number, "tester", wait_until,
        message="テストコード側の問題としての tester への差し戻し",
    )

    # 検証: 完了報告スレッドにトリアージ結果が返信追記され、Resolve 済み
    thread = _thread(gh_live, owner, repo, ctx["pr"].number, report)
    assert "> from: @architect" in (thread.body or ""), "トリアージ結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "implementer の完了報告が未 Resolve"

    # 検証: 指摘コメントが tester 宛で未解決のまま投稿されている
    pointed = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, "architect")
        if c.node_id != report.node_id
    ]
    assert pointed, "テストコードの誤りの指摘が投稿されていない"
    assert "> to: @tester" in (pointed[-1].body or ""), "指摘の宛先が tester でない"
    assert not server._is_minimized(pointed[-1].node_id), "指摘が Resolve されている"

    # 検証: architect がテストコード・実装コードを変更していない（修正は tester の担当）
    changed = _changed_files(gh_live, owner, repo, ctx["seed_sha"], ctx["subsystem_branch"])
    assert not [f for f in changed if f.startswith("src/") or f.startswith("tests/")], (
        f"テストコード / 実装コードが変更されている: {changed}"
    )
