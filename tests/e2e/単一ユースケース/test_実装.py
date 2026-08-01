"""「実装」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import supplement_review_comments
from tests.e2e.実装対象 import (
    IMPL_CONFLICT_MODULE_MD,
    MODULE_PATH,
    PROJECT_FILES,
    RED_TEST_PATH,
    RED_TEST_PY,
    run_branch_tests,
    seed_subsystem_branch,
    setup_subsystem,
)

# tester が作成済みの状態を再現する（テスト結果表の行あり・結果列は未記入）
SUBSYSTEM_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] `update_task` を実装
- [x] 単体テストを追加
- [ ] 単体テストを実行

## 単体テスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/tasks/test_service.py` | 全実行 | | 6 ケース（正常 2 / 異常 4） |

## 結合テスト結果

なし
"""

ASSIGN_COMMENT = """> from: @architect
> to: @implementer

テストレビューが完了したので、実装をお願いします。

Red のテストファイル:
- `tests/tasks/test_service.py`

実装の根拠になる設計ページ:
- `docs/wiki/設計図/インターフェース定義/バックエンド/タスク更新.py.md`
- `docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md`

モジュール構成の `#### 処理` の各ステップを関数内のコメントとして残してください。

---
"""


def test_normal(
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
    """タスク一覧の消化とテストの Green 化・Draft 解除・完了報告を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_sha = seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"], with_red_test=True
    )

    # 準備: architect の実装の割り当て → 確認:implementer 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ASSIGN_COMMENT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:implementer"]
    )

    # 実行: 実装の完了を待つ（確認:implementer 除去 + 確認:architect 付与）
    def _done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:architect" not in labels or "確認:implementer" in labels:
            return None
        return data

    data = wait_until(_done, timeout_sec=1800, message="実装の完了（確認:architect 付与 + 確認:implementer 除去）")

    # 検証: テスト結果表の結果列が全て ✅
    body = (data.body or "").replace("\r\n", "\n")
    assert "## 単体テスト結果" in body, "PR 本文に ## 単体テスト結果 がない"
    result_rows = [
        line for line in body.splitlines()
        if line.startswith("| `tests/") or line.startswith("| tests/")
    ]
    assert result_rows, "テスト結果表にテストファイルの行がない"
    for row in result_rows:
        assert "✅" in row, f"結果列が ✅ で埋まっていない: {row}"

    # 検証: 自分がやった実装の行だけがチェック済みで、テスト実行の行には触れていない
    impl_lines = [
        line.strip() for line in body.splitlines()
        if line.strip().startswith("- [") and "を実装" in line
    ]
    assert impl_lines and all(line.startswith("- [x]") for line in impl_lines), (
        f"実装タスクが未チェック: {impl_lines}"
    )
    run_lines = [
        line.strip() for line in body.splitlines()
        if line.strip().startswith("- [") and "テストを実行" in line
    ]
    assert all(line.startswith("- [ ]") for line in run_lines), (
        f"テスト実行の行に implementer がチェックを入れている: {run_lines}"
    )

    # 検証: テストが実際に Green になっている
    result = run_branch_tests(sandbox["local_path"], ctx["subsystem_branch"])
    assert result.returncode == 0, f"テストが Green になっていない:\n{result.stderr[-1500:]}"

    # 検証: PR が Ready（Draft 解除済み）
    pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=ctx["pr"].number).parsed_data
    assert pr_now.draft is False, "PR が Draft のまま（Draft 解除は implementer の担当）"

    # 検証: 実装コードが積まれ、Red テストは書き換えられていない
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert changed, "実装の commit が積まれていない"
    assert any(f.startswith("src/") for f in changed), f"src/ 配下の実装がない: {changed}"
    assert RED_TEST_PATH not in changed, f"Red テストが書き換えられている: {RED_TEST_PATH}"

    # 検証: architect 宛の完了報告が未 Resolve で投稿されている
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["pr"].number
    ).parsed_data
    reports = [c for c in comments if (c.body or "").lstrip().startswith("> from: @implementer")]
    assert reports, "implementer の完了報告コメントが投稿されていない"
    assert not server._is_minimized(reports[-1].node_id), "完了報告が Resolve されている（Resolve は architect の担当）"

    # 検証: commit 内容に対する補足事項がインラインコメントで残っている
    assert supplement_review_comments(gh_live, owner, repo, ctx["pr"].number), (
        "補足事項のインラインコメントが投稿されていない"
    )

    # 検証: 議論中 / assignee なし（ユーザーとの会話を持たない）
    labels = {label.name for label in data.labels}
    assert "議論中" not in labels, "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"


def test_normal_when_reverse(
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
    """現状の実装をあるべき構造へ寄せる実装を実環境で確認する（正常系・リバースエンジニアリング）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_sha = seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])
    # RE 経路なので現状の実装コードが既にある（あるべき構造へ寄せるのが今回の実装）
    for path, content in PROJECT_FILES.items():
        commit_file(ctx["subsystem_branch"], path, content, f"chore: e2e 用に {path} を配置")
    commit_file(
        ctx["subsystem_branch"], RED_TEST_PATH, RED_TEST_PY, "test: 単体テストを追加"
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["subsystem"].number, labels=["リバースエンジニアリング"]
    )

    # 準備: architect の実装の割り当て → 確認:implementer 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ASSIGN_COMMENT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:implementer"]
    )

    # 実行: 実装の完了を待つ
    def _done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:architect" not in labels or "確認:implementer" in labels:
            return None
        return data

    data = wait_until(_done, timeout_sec=1800, message="実装の完了（RE 経路）")

    # 検証: 実装が積まれ、テストコードは書き換えられていない
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert any(f.startswith("src/") for f in changed), f"src/ 配下の実装がない: {changed}"

    # 検証: テスト結果表の結果列が未記入で、PR は Draft のまま（どちらも architect の担当）
    body = (data.body or "").replace("\r\n", "\n")
    assert "✅" not in body, "結果列が記入されている（記入は architect の担当）"
    pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=ctx["pr"].number).parsed_data
    assert pr_now.draft is True, "PR の Draft が解除されている（解除は architect の担当）"

    # 検証: architect 宛の完了報告が未 Resolve で投稿されている
    reports = [
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=ctx["pr"].number
        ).parsed_data
        if (c.body or "").lstrip().startswith("> from: @implementer")
    ]
    assert reports, "implementer の完了報告コメントが投稿されていない"
    assert not server._is_minimized(reports[-1].node_id), "完了報告が Resolve されている"

    # 検証: commit 内容に対する補足事項がインラインコメントで残っている
    assert supplement_review_comments(gh_live, owner, repo, ctx["pr"].number), (
        "補足事項のインラインコメントが投稿されていない"
    )


def test_error_when_design_decision_needed(
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
    """設計 Wiki だけでは決まらない判断を検知したときの差し戻しを確認する（異常系・設計レベルの判断が必要）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    # 準備: 実装がレビュー済みテストと両立しないモジュール構成を積む
    seed_sha = seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"], with_red_test=True,
        design_overrides={MODULE_PATH: IMPL_CONFLICT_MODULE_MD},
    )

    # 準備: architect の実装の割り当て → 確認:implementer 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ASSIGN_COMMENT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:implementer"]
    )

    # 実行: architect への差し戻しを待つ
    def _bounced():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:architect" not in labels or "確認:implementer" in labels:
            return None
        return data

    wait_until(_bounced, timeout_sec=1800, message="設計レベルの判断を求める差し戻し")

    # 検証: 差し戻し報告が architect 宛で未解決のまま投稿されている
    reports = [
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=ctx["pr"].number
        ).parsed_data
        if (c.body or "").lstrip().startswith("> from: @implementer")
    ]
    assert reports, "implementer の差し戻し報告が投稿されていない"
    assert "> to: @architect" in (reports[-1].body or ""), "差し戻し報告の宛先が architect でない"
    assert not server._is_minimized(reports[-1].node_id), "差し戻し報告が Resolve されている"

    # 検証: 実装コードを commit していない（差し戻しなので着手しない）
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert not [f for f in changed if f.startswith("src/")], (
        f"差し戻しなのに実装コードが commit されている: {changed}"
    )
