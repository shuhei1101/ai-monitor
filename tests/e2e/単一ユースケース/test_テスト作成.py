"""「テスト作成」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import supplement_review_comments
from tests.e2e.実装対象 import (
    MODULE_PATH,
    PROJECT_FILES,
    SUBSYSTEM_PR_BODY,
    TESTER_CONFLICT_MODULE_MD,
    run_branch_tests,
    seed_subsystem_branch,
    setup_subsystem,
)

ASSIGN_COMMENT = """> from: @architect
> to: @tester

設計 Wiki が確定したので、テスト作成をお願いします。

確定した設計ページ:
- `docs/wiki/設計図/インターフェース定義/バックエンド/タスク更新.py.md`
- `docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md`

テスト観点の起点は上記 2 ページです。モジュール構成の `#### 単体テスト` 表と、結合の `## 正常系` / `## 異常系` を漏れなくケース化してください。

---
"""

TEST_RESULT_SECTIONS = [
    "## 単体テスト結果",
    "## 結合テスト結果",
]


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
    """設計 Wiki を元にした Red テストの作成と architect への完了報告を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_sha = seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])

    # 準備: architect のテスト作成の割り当て → 確認:tester 付与（起動トリガー）
    assign = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ASSIGN_COMMENT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:tester"]
    )

    # 実行: テスト作成の完了を待つ（確認:tester 除去 + 確認:architect 付与）
    def _done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:architect" not in labels or "確認:tester" in labels:
            return None
        return data

    data = wait_until(_done, timeout_sec=1800, message="テスト作成の完了（確認:architect 付与 + 確認:tester 除去）")

    # 検証: テスト結果表が新設され、結果列は未記入
    body = (data.body or "").replace("\r\n", "\n")
    for section in TEST_RESULT_SECTIONS:
        assert section in body, f"PR 本文に {section} がない"
    assert "✅" not in body, "結果列が記入されている（記入は implementer の担当）"

    # 検証: タスク一覧のチェックが未変更（チェックは architect が検収時に入れる）
    assert "- [x]" not in body, "タスク一覧にチェックが入っている"

    # 検証: commit がテストコードだけで、実装コードを含まない
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert changed, "テストコードの commit が積まれていない"
    assert any(f.startswith("tests/") for f in changed), f"tests/ 配下の追加がない: {changed}"
    impl = [f for f in changed if f.startswith("src/")]
    assert not impl, f"実装コードが含まれている（implementer の領分）: {impl}"

    # 検証: テストファイル名が本文のテスト結果表に載っている
    test_files = [f for f in changed if f.startswith("tests/") and f.endswith(".py")]
    assert any(f in body for f in test_files), f"テスト結果表にテストファイル名がない: {test_files}"

    # 検証: テストを実行すると想定どおり fail する（Red）
    result = run_branch_tests(sandbox["local_path"], ctx["subsystem_branch"])
    assert result.returncode != 0, f"テストが Red になっていない:\n{result.stderr[-1500:]}"

    # 検証: architect 宛の完了報告が未 Resolve で投稿されている
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["pr"].number
    ).parsed_data
    reports = [c for c in comments if (c.body or "").lstrip().startswith("> from: @tester")]
    assert reports, "tester の完了報告コメントが投稿されていない"
    assert not server._is_minimized(reports[-1].node_id), "完了報告が Resolve されている（Resolve は architect の担当）"

    # 検証: commit 内容に対する補足事項がインラインコメントで残っている
    assert supplement_review_comments(gh_live, owner, repo, ctx["pr"].number), (
        "補足事項のインラインコメントが投稿されていない"
    )

    # 検証: 議論中 / assignee なし（ユーザーとの会話を持たない）
    labels = {label.name for label in data.labels}
    assert "議論中" not in labels, "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"
    assert assign is not None


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
    """現状の実装がある状態でのテスト作成を実環境で確認する（正常系・リバースエンジニアリング）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_sha = seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])
    # RE 経路なので、あるべき構造の設計 Wiki に加えて現状の実装コードが既にある
    for path, content in PROJECT_FILES.items():
        commit_file(ctx["subsystem_branch"], path, content, f"chore: e2e 用に {path} を配置")
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["subsystem"].number, labels=["リバースエンジニアリング"]
    )

    # 準備: architect のテスト作成の割り当て → 確認:tester 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ASSIGN_COMMENT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:tester"]
    )

    # 実行: テスト作成の完了を待つ
    def _done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:architect" not in labels or "確認:tester" in labels:
            return None
        return data

    data = wait_until(_done, timeout_sec=1800, message="テスト作成の完了（RE 経路）")

    # 検証: commit がテストコードだけで、現状の実装コードを書き換えていない
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    impl = [f for f in changed if f.startswith("src/")]
    assert not impl, f"実装コードが変更されている（RE 経路でも tester は触らない）: {impl}"
    assert any(f.startswith("tests/") for f in changed), f"tests/ 配下の追加がない: {changed}"

    # 検証: 既存の振る舞いを固定するテストとあるべき構造を突くテストが完了報告で区別されている
    reports = [
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=ctx["pr"].number
        ).parsed_data
        if (c.body or "").lstrip().startswith("> from: @tester")
    ]
    assert reports, "tester の完了報告コメントが投稿されていない"
    report_body = reports[-1].body or ""
    assert any(word in report_body for word in ("現状", "既存", "あるべき")), (
        f"既存の振る舞いとあるべき構造の区別が完了報告にない: {report_body[:200]}"
    )

    # 検証: 結果列は未記入のまま（実行は architect の担当）
    body = (data.body or "").replace("\r\n", "\n")
    assert "✅" not in body, "結果列が記入されている（実行は architect の担当）"

    # 検証: commit 内容に対する補足事項がインラインコメントで残っている
    assert supplement_review_comments(gh_live, owner, repo, ctx["pr"].number), (
        "補足事項のインラインコメントが投稿されていない"
    )


def test_error_when_revision_needed(
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
    """設計 Wiki の構造問題を検知したときの architect への差し戻しを確認する（異常系・設計の見直しが必要）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    # 準備: テストの構造が設計から決められないモジュール構成を積む
    seed_sha = seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        design_overrides={MODULE_PATH: TESTER_CONFLICT_MODULE_MD},
    )

    # 準備: architect のテスト作成の割り当て → 確認:tester 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ASSIGN_COMMENT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:tester"]
    )

    # 実行: architect への差し戻しを待つ
    def _bounced():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:architect" not in labels or "確認:tester" in labels:
            return None
        return data

    wait_until(_bounced, timeout_sec=1800, message="設計の見直しを求める差し戻し")

    # 検証: 差し戻し報告が architect 宛で未解決のまま投稿されている
    reports = [
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=ctx["pr"].number
        ).parsed_data
        if (c.body or "").lstrip().startswith("> from: @tester")
    ]
    assert reports, "tester の差し戻し報告が投稿されていない"
    assert "> to: @architect" in (reports[-1].body or ""), "差し戻し報告の宛先が architect でない"
    assert not server._is_minimized(reports[-1].node_id), "差し戻し報告が Resolve されている"

    # 検証: テストコードを commit していない（差し戻しなので着手しない）
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert not [f for f in changed if f.startswith("tests/")], (
        f"差し戻しなのにテストコードが commit されている: {changed}"
    )
