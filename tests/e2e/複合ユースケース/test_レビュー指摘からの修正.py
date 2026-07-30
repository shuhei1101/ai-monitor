"""「レビュー指摘からの修正」の E2E テスト。"""
from __future__ import annotations

import base64

import ai_monitor.mcp.server as server
from tests.e2e.実装対象 import (
    DEVIATING_MODELS_PY,
    DEVIATING_SERVICE_PY,
    INCOMPLETE_TEST_PY,
    RED_TEST_PATH,
    RED_TEST_PY,
    branch_sha,
    count_test_functions,
    run_branch_tests,
    seed_subsystem_branch,
    setup_subsystem,
)


def _pr_body(result: str) -> str:
    """tester がテスト結果表を新設済みの subsystem PR 本文を組み立てる。"""
    return f"""## 紐づく Issue

- #{{subsystem_number}}

## タスク一覧

- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] `update_task` を実装
- [ ] 単体テストを作成して実行

## 単体テスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/tasks/test_service.py` | 全実行 | {result} | - |

## 結合テスト結果

なし
"""

TESTER_REPORT = """> from: @tester
> to: @architect

テスト作成が完了しました。

- 作成したテストファイル: `tests/tasks/test_service.py`
- 元にした設計ページ: `docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md`
- 実行結果: 想定どおり fail（`update_task` が未実装のため import エラー）

| commit | 内容 |
| --- | --- |
| seed | 単体テストを追加 |

---
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


def _label_and_assignee_events(gh_live, owner, repo, number):
    """PR のラベル付与・assignee 設定イベントを返す。"""
    events = gh_live.rest.issues.list_events_for_timeline(
        owner=owner, repo=repo, issue_number=number, per_page=100
    ).parsed_data
    labeled = [e for e in events if getattr(e, "event", "") == "labeled"]
    assigned = [e for e in events if getattr(e, "event", "") == "assigned"]
    return labeled, assigned


def test_normal_when_test_review(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    subsystem_issue_factory,
    commit_file,
    wait_until,
    sandbox,
):
    """テストレビュー指摘 → tester 修正 → 再レビューの収束を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=_pr_body(" "),
    )
    # 異常系 3 ケースが欠落したテストを積む（architect の指摘を誘発）
    seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])
    commit_file(
        ctx["subsystem_branch"], "tests/tasks/__init__.py", "", "chore: e2e 用のテストパッケージを配置"
    )
    commit_file(
        ctx["subsystem_branch"], RED_TEST_PATH, INCOMPLETE_TEST_PY,
        "test: 単体テストを追加（異常系の一部が欠落した状態）",
    )
    seed_sha = branch_sha(gh_live, owner, repo, ctx["subsystem_branch"])

    # 準備: tester の完了報告 → 確認:architect 付与（テストレビューの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=TESTER_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    # 実行: 指摘 → 修正 → 再レビューのループが収束するまで待つ（確認:implementer 付与が終端）
    # 収束時点の sha を掴んでおく（この直後に implementer が起動して実装を push するため）
    def _converged():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:implementer" not in labels:
            return None
        return data, branch_sha(gh_live, owner, repo, ctx["subsystem_branch"])

    data, converged_sha = wait_until(
        _converged, timeout_sec=3600, message="指摘 → 修正 → 再レビューの収束（確認:implementer 付与）"
    )

    # 検証: インライン指摘が投稿されている
    review_comments = gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=ctx["pr"].number
    ).parsed_data
    assert review_comments, "インライン指摘が投稿されていない（指摘なしで通過した可能性）"

    # 検証: 往復が完了報告スレッドに記録され、Resolve 済み
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["pr"].number
    ).parsed_data
    thread = next((c for c in comments if c.node_id == report.node_id), None)
    assert thread is not None, "tester の完了報告コメントが見つからない"
    body = thread.body or ""
    assert "> from: @architect" in body, "スレッドに architect の返信が追記されていない"
    assert "> from: @tester" in body.split("> from: @architect", 1)[1], "スレッドに tester の修正報告がない"
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    # 検証: 欠落していた異常系ケースが補われている（設計 Wiki の単体テスト表と同じ 6 件）
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{converged_sha}"
    ).parsed_data
    test_files = [
        f.filename for f in (compare.files or [])
        if f.filename.startswith("tests/") and f.filename.endswith(".py")
        and not f.filename.endswith("__init__.py")
    ]
    assert test_files, "テスト修正の commit が積まれていない"
    cases = count_test_functions(gh_live, owner, repo, test_files, converged_sha)
    assert cases >= 6, f"単体テスト表の 6 ケースに揃っていない（{cases} 件）: {test_files}"

    # 検証: 実装は入っていないので Red のまま
    result = run_branch_tests(sandbox["local_path"], ctx["subsystem_branch"], ref=converged_sha)
    assert result.returncode != 0, "テストが Red のままでない（実装が混入した可能性）"

    # 検証: タスク一覧のテスト作成タスクがチェック済み
    pr_body = (data.body or "").replace("\r\n", "\n")
    test_task = [line for line in pr_body.splitlines() if "単体テストを作成して実行" in line]
    assert test_task and test_task[0].startswith("- [x]"), f"テスト作成タスクが未チェック: {test_task}"

    # 検証: ループ中にユーザー操作を求めていない
    labeled, assigned = _label_and_assignee_events(gh_live, owner, repo, ctx["pr"].number)
    assert not [e for e in labeled if getattr(e.label, "name", "") == "議論中"], "議論中 が付与された"
    assert not assigned, "assignee が設定された（ユーザー操作を求めている）"


def test_normal_when_impl_review(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    subsystem_issue_factory,
    commit_file,
    wait_until,
    sandbox,
):
    """実装レビュー指摘 → implementer 修正 → 再レビュー → マージ起動を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=_pr_body("✅"),
    )
    # 設計どおりのテスト（全 6 ケース）と、設計に無い updated_at を返す実装を積む
    seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])
    commit_file(ctx["subsystem_branch"], "tests/tasks/__init__.py", "", "chore: e2e 用のテストパッケージを配置")
    commit_file(ctx["subsystem_branch"], RED_TEST_PATH, RED_TEST_PY, "test: 単体テストを追加")
    commit_file(ctx["subsystem_branch"], "src/tasks/models.py", DEVIATING_MODELS_PY, "feat: Task に項目を追加")
    commit_file(ctx["subsystem_branch"], "src/tasks/service.py", DEVIATING_SERVICE_PY, "feat: update_task を実装")
    gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=ctx["pr"].number, draft=False)

    # 準備: implementer の完了報告 → 確認:architect 付与（実装レビューの起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=IMPLEMENTER_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    # 実行: 指摘 → 修正 → 再レビュー → 一式完了報告 → マージ起動の待機まで進むのを待つ
    def _merge_gate_open():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    data = wait_until(
        _merge_gate_open, timeout_sec=3600, message="マージ起動の最終確認ゲート（議論中 + assignee）"
    )

    # 検証: インライン指摘が投稿されている
    review_comments = gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=ctx["pr"].number
    ).parsed_data
    assert review_comments, "インライン指摘が投稿されていない（指摘なしで通過した可能性）"

    # 検証: 往復が完了報告スレッドに記録され、Resolve 済み
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["pr"].number
    ).parsed_data
    thread = next((c for c in comments if c.node_id == report.node_id), None)
    assert thread is not None, "implementer の完了報告コメントが見つからない"
    body = thread.body or ""
    assert "> from: @architect" in body, "スレッドに architect の返信が追記されていない"
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    # 検証: 設計に無い項目が除去され、テストは Green のまま
    result = run_branch_tests(sandbox["local_path"], ctx["subsystem_branch"])
    assert result.returncode == 0, f"テストが Green でない:\n{result.stderr[-1500:]}"
    models = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path="src/tasks/models.py", ref=ctx["subsystem_branch"]
    ).parsed_data
    models_py = base64.b64decode(models.content).decode("utf-8")
    assert "updated_at" not in models_py, "設計に無い updated_at が残っている（指摘が反映されていない）"

    # 検証: タスク一覧が全てチェック済み + テスト結果表が全 ✅ のまま
    pr_body = (data.body or "").replace("\r\n", "\n")
    assert "- [ ]" not in pr_body, "タスク一覧に未チェックの行が残っている"
    result_rows = [line for line in pr_body.splitlines() if line.startswith("| `tests/")]
    assert result_rows, "テスト結果表にテストファイルの行がない"
    for row in result_rows:
        assert "✅" in row, f"テスト結果表が全 ✅ でない: {row}"

    # 検証: マージ前の最終確認依頼が投稿されている（マージは実行されていない）
    assert any(
        (c.body or "").lstrip().startswith("> from: @subsystem-conductor") for c in comments
    ), "subsystem-conductor の最終確認依頼が投稿されていない"
    pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=ctx["pr"].number).parsed_data
    assert pr_now.merged is False, "ユーザー最終確認の前にマージされている"
