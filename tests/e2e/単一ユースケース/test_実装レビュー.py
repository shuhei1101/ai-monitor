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
    IMPLEMENTED_SERVICE_PY,
    MODELS_PY,
    RED_TEST_PATH,
    RED_TEST_PY,
    run_branch_tests,
    seed_subsystem_branch,
    setup_subsystem,
)

PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] `update_task` を実装
- [x] 単体テストを作成して実行

## 単体テスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/tasks/test_service.py` | 全実行 | ✅ | 6 ケース |

## 結合テスト結果

なし
"""

IMPLEMENTER_REPORT = """> from: @implementer
> to: @architect

実装が完了しました。

- 消化したタスク: `update_task` の実装
- テストの実行結果: 全 6 ケース Green
- Draft を解除済み

| commit | 内容 |
| --- | --- |
| seed | update_task を実装 |

---
"""


def _setup(gh_live, owner, repo, factories, commit_file, *, models: str, service: str):
    """実装完了時点の subsystem PR 一式を用意する。"""
    ctx = setup_subsystem(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["draft_pr_factory"],
        factories["story_issue_factory"], factories["subsystem_issue_factory"], commit_file,
        pr_body=PR_BODY,
    )
    seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])
    commit_file(ctx["subsystem_branch"], "tests/tasks/__init__.py", "", "chore: e2e 用のテストパッケージを配置")
    commit_file(ctx["subsystem_branch"], RED_TEST_PATH, RED_TEST_PY, "test: 単体テストを追加")
    commit_file(ctx["subsystem_branch"], "src/tasks/models.py", models, "feat: Task を更新")
    commit_file(ctx["subsystem_branch"], "src/tasks/service.py", service, "feat: update_task を実装")
    gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=ctx["pr"].number, draft=False)
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


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """設計どおりの実装を指摘なしで通し subsystem-conductor へ一式完了報告することを確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx, report = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, models=MODELS_PY, service=IMPLEMENTED_SERVICE_PY,
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
    thread = next(c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id)
    assert "> from: @architect" in (thread.body or ""), "レビュー結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    # 検証: タスク一覧が全チェック済み
    body = (data.body or "").replace("\r\n", "\n")
    assert "- [ ]" not in body, "タスク一覧に未チェックの行が残っている"

    # 検証: 一式完了報告が subsystem-conductor 宛で未解決のまま投稿されている
    handoffs = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, "architect")
        if c.node_id != report.node_id
    ]
    assert handoffs, "一式完了報告が投稿されていない"
    assert "> to: @subsystem-conductor" in (handoffs[-1].body or ""), "一式完了報告の宛先が違う"
    assert not server._is_minimized(handoffs[-1].node_id), "一式完了報告が Resolve されている"


def test_error_pointed_out(
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
    thread = next(c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id)
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
