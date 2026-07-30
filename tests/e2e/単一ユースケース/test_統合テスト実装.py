"""「統合テスト実装」の E2E テスト。

UC は単一 UC（story レベル）で代表して書かれているが、読み替え先の複合 UC（epic レベル）も
別エージェントの実体なので、両レベルとも実行する。
"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import supplement_review_comments
from tests.e2e.統合テスト import (
    EPIC_PR_BODY,
    SCENARIO_MD_CONFLICTING,
    STORY_PR_BODY,
    epic_branch_files,
    result_rows,
    setup_epic,
    setup_story,
    story_branch_files,
)
from tests.e2e.実装対象 import SCENARIO_PATH, add_worktree, branch_sha

# 読み替え表（UC の「図の表記 / 複合 UC での読み替え」に対応）
SINGLE = {
    "tester": "single-scenario-tester",
    "writer": "single-scenario-writer",
    "section": "## 単一ユースケースシナリオテスト結果",
    "e2e_dir": "tests/e2e/単一ユースケース/",
}
COMPLEX = {
    "tester": "complex-scenario-tester",
    "writer": "complex-scenario-writer",
    "section": "## 複合ユースケースシナリオテスト結果",
    "e2e_dir": "tests/e2e/複合ユースケース/",
}


def _issue(gh_live, owner, repo, number):
    """Issue / PR の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def _confirm_labels(data) -> list[str]:
    """スナップショットの確認ラベルだけを返す。"""
    return sorted(label.name for label in data.labels if label.name.startswith("確認:"))


def _wait_handed_back(gh_live, owner, repo, pr_number, wait_until, level, *, message):
    """指揮役への引き渡し（`確認:{writer}` 付与 + 報告）を待つ。"""

    def _done():
        data = _issue(gh_live, owner, repo, pr_number)
        labels = {label.name for label in data.labels}
        if f"確認:{level['writer']}" not in labels or f"確認:{level['tester']}" in labels:
            return None
        reports = [
            c for c in gh_live.rest.issues.list_comments(
                owner=owner, repo=repo, issue_number=pr_number
            ).parsed_data
            if (c.body or "").lstrip().startswith(f"> from: @{level['tester']}")
        ]
        return (data, reports[-1]) if reports else None

    return wait_until(_done, timeout_sec=2400, message=message)


def _assert_handed_back(data, report, level) -> None:
    """指揮役宛の報告が未 Resolve で、確認ラベルが指揮役の 1 つだけであることを検証する。"""
    assert f"> to: @{level['writer']}" in (report.body or ""), "報告の宛先が指揮役になっていない"
    assert not server._is_minimized(report.node_id), "報告が Resolve されている（受領は指揮役が行う）"
    assert _confirm_labels(data) == [f"確認:{level['writer']}"], (
        f"確認ラベルが 確認:{level['writer']} だけになっていない: {_confirm_labels(data)}"
    )


def _assert_implemented(gh_live, owner, repo, branch, seed_sha, data, level) -> None:
    """テスト実装の成果（E2E テストの commit + 結果列未記入の結果表）を検証する。"""
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{branch}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    e2e_files = [
        f for f in changed
        if f.startswith(level["e2e_dir"]) and f.endswith(".py") and not f.endswith("__init__.py")
    ]
    assert e2e_files, f"E2E テストコードが commit されていない: {changed}"

    body = (data.body or "").replace("\r\n", "\n")
    assert level["section"] in body, "テスト結果表のセクションが新設されていない"
    rows = result_rows(body, section_name=level["section"])
    assert len(rows) >= 2, f"新規 + 回帰の行が並んでいない: {rows}"
    assert any(f in body for f in e2e_files), f"新規テストの行がない: {e2e_files}"
    assert "✅" not in body and "❌" not in body, "結果列が記入されている（記入は実行フェーズ）"
    assert supplement_review_comments(gh_live, owner, repo, data.number), (
        "補足事項のインラインコメントが投稿されていない"
    )
    assert "議論中" not in {label.name for label in data.labels}, "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"


def test_normal_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """単一 UC シナリオの E2E テスト化と回帰対象の洗い出しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_story(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file,
        pr_body=STORY_PR_BODY, files=story_branch_files(),
    )
    add_worktree(sandbox["local_path"], ctx["story_branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["story_branch"])

    # 準備: 指揮役の割り当て（確認ラベルのみ・実行指示コメントなし = 実装フェーズ）
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=[f"確認:{SINGLE['tester']}"]
    )

    # 実行: テスト実装の完了を待つ
    data, report = _wait_handed_back(
        gh_live, owner, repo, ctx["pr"].number, wait_until, SINGLE, message="テスト実装の完了",
    )

    # 検証
    _assert_implemented(gh_live, owner, repo, ctx["story_branch"], seed_sha, data, SINGLE)
    _assert_handed_back(data, report, SINGLE)


def test_normal_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, commit_file, wait_until, sandbox,
):
    """複合 UC シナリオの E2E テスト化と回帰対象の洗い出しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_epic(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory, commit_file,
        pr_body=EPIC_PR_BODY, files=epic_branch_files(),
    )
    add_worktree(sandbox["local_path"], ctx["epic_branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["epic_branch"])

    # 準備: 指揮役の割り当て（確認ラベルのみ・実行指示コメントなし = 実装フェーズ）
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=[f"確認:{COMPLEX['tester']}"]
    )

    # 実行: テスト実装の完了を待つ
    data, report = _wait_handed_back(
        gh_live, owner, repo, ctx["pr"].number, wait_until, COMPLEX, message="テスト実装の完了",
    )

    # 検証
    _assert_implemented(gh_live, owner, repo, ctx["epic_branch"], seed_sha, data, COMPLEX)
    _assert_handed_back(data, report, COMPLEX)


def test_error_revision_needed(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ設計書の構造問題を検知したときの差し戻しを実環境で確認する（異常系・設計書の見直しが必要）。"""
    owner, repo = repo_ctx
    ctx = setup_story(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file,
        pr_body=STORY_PR_BODY, files=story_branch_files(),
    )
    # story のユースケース要件と矛盾したシナリオを置き、設計書どおりに書けない状態を誘発する
    commit_file(
        ctx["story_branch"], SCENARIO_PATH, SCENARIO_MD_CONFLICTING,
        "docs: 単一UC シナリオを要件と矛盾した内容に差し替え",
    )
    add_worktree(sandbox["local_path"], ctx["story_branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["story_branch"])

    # 準備: 指揮役の割り当て（確認ラベルのみ = 実装フェーズ）
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=[f"確認:{SINGLE['tester']}"]
    )

    # 実行: 指揮役への差し戻し報告を待つ
    data, report = _wait_handed_back(
        gh_live, owner, repo, ctx["pr"].number, wait_until, SINGLE, message="シナリオ差し戻しの報告",
    )

    # 検証: E2E テストコードが commit されていない
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['story_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    e2e_files = [
        f for f in changed
        if f.startswith(SINGLE["e2e_dir"]) and f.endswith(".py") and not f.endswith("__init__.py")
    ]
    assert not e2e_files, f"差し戻しなのに E2E テストコードが commit されている: {e2e_files}"

    # 検証: 差し戻し報告に理由が書かれ、未解決のまま指揮役へ渡っている
    body = report.body or ""
    assert any(word in body for word in ("シナリオ", "設計書", "矛盾")), (
        f"差し戻しの理由が報告に書かれていない: {body[:200]}"
    )
    _assert_handed_back(data, report, SINGLE)
