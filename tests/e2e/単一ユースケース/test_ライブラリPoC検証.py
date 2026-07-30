"""「ライブラリPoC検証」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import supplement_review_comments
from tests.e2e.ライブラリPoC import (
    POC_CODE,
    POC_CODE_PATH,
    POC_PR_BODY,
    POC_PR_BODY_DONE,
    POC_PR_BODY_UNMET,
    PREVIOUS_REPORT,
    REVERIFY_INSTRUCTION,
    VERIFY_INSTRUCTION,
    result_rows,
    setup_poc_pr,
)
from tests.e2e.実装対象 import add_worktree, branch_sha


def _issue(gh_live, owner, repo, number):
    """Issue / PR の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def _confirm_labels(data) -> list[str]:
    """スナップショットの確認ラベルだけを返す。"""
    return sorted(label.name for label in data.labels if label.name.startswith("確認:"))


def _cells(row: str) -> list[str]:
    """表の 1 行をセル配列（観点 / 成功条件 / 実測値 / 判定 / 補足）に分解する。"""
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _runner_reports(gh_live, owner, repo, number) -> list:
    """library-poc-runner 起点のコメントを投稿順で返す。"""
    return [
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=number
        ).parsed_data
        if (c.body or "").lstrip().startswith("> from: @library-poc-runner")
    ]


def _wait_handed_back(gh_live, owner, repo, poc_number, wait_until, *, exclude_node_id=None, message=""):
    """発注元への引き渡し（確認:architect 付与 + 完了報告）を待って (本文, 完了報告) を返す。"""

    def _done():
        data = _issue(gh_live, owner, repo, poc_number)
        labels = {label.name for label in data.labels}
        if "確認:architect" not in labels or "確認:library-poc-runner" in labels:
            return None
        reports = [
            c for c in _runner_reports(gh_live, owner, repo, poc_number)
            if c.node_id != exclude_node_id
        ]
        return (data, reports[-1]) if reports else None

    return wait_until(_done, timeout_sec=1800, message=message)


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
    """検証指示を受けた PoC の実装・実行・結果記録と発注元への完了報告を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_poc_pr(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        poc_body=POC_PR_BODY,
    )
    add_worktree(sandbox["local_path"], ctx["poc_branch"])
    seed_sha = branch_sha(gh_live, owner, repo, ctx["poc_branch"])

    # 準備: 発注元の検証指示 → 確認:library-poc-runner 付与（起動トリガー）
    instruction = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["poc_pr"].number, body=VERIFY_INSTRUCTION
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["poc_pr"].number, labels=["確認:library-poc-runner"]
    )

    # 実行: 検証完了を待つ（確認:architect 付与 + 確認:library-poc-runner 除去 + 完了報告）
    data, report = _wait_handed_back(
        gh_live, owner, repo, ctx["poc_pr"].number, wait_until,
        message="PoC 検証の完了（確認:architect 付与 + 完了報告）",
    )

    # 検証: 検証指示が Resolve され、発注元宛の完了報告が未 Resolve（受領は発注元の担当）
    assert server._is_minimized(instruction.node_id), "検証指示コメントが Resolve されていない"
    assert "> to: @architect" in (report.body or ""), "完了報告の宛先が発注元になっていない"
    assert not server._is_minimized(report.node_id), "完了報告が Resolve されている（受領は発注元が行う）"

    # 検証: 検証観点と結果の全行に実測値と判定が入っている
    body = (data.body or "").replace("\r\n", "\n")
    rows = result_rows(body)
    assert rows, "検証観点と結果の行がない"
    for row in rows:
        assert "✅" in row, f"成功条件を満たす想定の観点が ✅ になっていない: {row}"
    assert "所感" in body, "所感が記録されていない"
    assert "## 最小再現コード" in body, "最小再現コードが記録されていない"

    # 検証: PoC コードが PoC ブランチに commit されている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['poc_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert changed, "PoC コードの commit が積まれていない"

    # 検証: commit 内容に対する補足事項がインラインコメントで残っている
    assert supplement_review_comments(gh_live, owner, repo, ctx["poc_pr"].number), (
        "補足事項のインラインコメントが投稿されていない"
    )

    # 検証: 確認ラベルが architect の 1 つだけで、ユーザーとの会話を持たない
    assert _confirm_labels(data) == ["確認:architect"], (
        f"確認ラベルが 確認:architect だけになっていない: {_confirm_labels(data)}"
    )
    assert "議論中" not in {label.name for label in data.labels}, "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"


def test_normal_when_reverify(
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
    """再検証指示を受けた追加観点の実行と結果の追記を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_poc_pr(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        poc_body=POC_PR_BODY_DONE, poc_files={POC_CODE_PATH: POC_CODE},
    )
    add_worktree(sandbox["local_path"], ctx["poc_branch"])

    # 準備: 初回検証の完了報告（発注元が受領して Resolve 済み）
    previous = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["poc_pr"].number, body=PREVIOUS_REPORT
    ).parsed_data
    server._minimize_comment(previous.node_id)

    # 準備: 発注元の再検証指示 → 確認:library-poc-runner 再付与（起動トリガー）
    instruction = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["poc_pr"].number, body=REVERIFY_INSTRUCTION
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["poc_pr"].number, labels=["確認:library-poc-runner"]
    )

    # 実行: 再検証の完了を待つ（初回の完了報告とは別のコメントが終端の目印）
    data, report = _wait_handed_back(
        gh_live, owner, repo, ctx["poc_pr"].number, wait_until,
        exclude_node_id=previous.node_id, message="再検証の完了（確認:architect 付与 + 完了報告）",
    )

    # 検証: 再検証指示が Resolve され、発注元宛の完了報告が未 Resolve
    assert server._is_minimized(instruction.node_id), "再検証指示コメントが Resolve されていない"
    assert "> to: @architect" in (report.body or ""), "完了報告の宛先が発注元になっていない"
    assert not server._is_minimized(report.node_id), "完了報告が Resolve されている（受領は発注元が行う）"

    # 検証: 追加観点の行が足され、既存の観点も残っている
    body = (data.body or "").replace("\r\n", "\n")
    rows = result_rows(body)
    assert len(rows) >= 4, f"追加観点の行が足されていない: {rows}"
    rollback = [row for row in rows if "ロールバック" in row]
    assert rollback, f"ロールバックの観点が追加されていない: {rows}"
    assert "✅" in rollback[0], f"追加観点の判定が記入されていない: {rollback[0]}"
    for keyword in ("インメモリ DB の CRUD", "一括挿入の性能", "型の往復"):
        assert any(keyword in row for row in rows), f"既存の観点が消えている: {keyword}"

    # 検証: 確認ラベルが architect の 1 つだけ
    assert _confirm_labels(data) == ["確認:architect"], (
        f"確認ラベルが 確認:architect だけになっていない: {_confirm_labels(data)}"
    )


def test_error_when_unmet(
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
    """成功条件を満たさない観点の NG 記録と発注元への報告を実環境で確認する（異常系）。"""
    owner, repo = repo_ctx
    ctx = setup_poc_pr(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        poc_body=POC_PR_BODY_UNMET,
    )
    add_worktree(sandbox["local_path"], ctx["poc_branch"])

    # 準備: 発注元の検証指示 → 確認:library-poc-runner 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["poc_pr"].number, body=VERIFY_INSTRUCTION
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["poc_pr"].number, labels=["確認:library-poc-runner"]
    )

    # 実行: 検証完了を待つ（確認:architect 付与 + 確認:library-poc-runner 除去 + 完了報告）
    data, report = _wait_handed_back(
        gh_live, owner, repo, ctx["poc_pr"].number, wait_until,
        message="PoC 検証の完了（確認:architect 付与 + 完了報告）",
    )

    # 検証: 満たせない観点が ❌ で、実測値に理由が記録されている
    body = (data.body or "").replace("\r\n", "\n")
    rows = result_rows(body)
    unmet = [row for row in rows if "非同期クエリ" in row]
    assert unmet, f"非同期クエリの観点が消えている: {rows}"
    cells = _cells(unmet[0])
    assert "❌" in cells[3], f"満たせない観点が ❌ になっていない: {unmet[0]}"
    assert cells[2] != "-", f"NG の実測値が未記入のまま: {unmet[0]}"

    # 検証: 発注元宛の完了報告が未 Resolve で投稿されている
    assert "> to: @architect" in (report.body or ""), "完了報告の宛先が発注元になっていない"
    assert not server._is_minimized(report.node_id), "完了報告が Resolve されている（受領は発注元が行う）"

    # 検証: PoC PR は open のまま（採用可否の判断は発注元）
    pr_now = gh_live.rest.pulls.get(
        owner=owner, repo=repo, pull_number=ctx["poc_pr"].number
    ).parsed_data
    assert pr_now.state == "open", "PoC PR が close されている（close は発注元の担当）"

    # 検証: 確認ラベルが architect の 1 つだけ
    assert _confirm_labels(data) == ["確認:architect"], (
        f"確認ラベルが 確認:architect だけになっていない: {_confirm_labels(data)}"
    )
