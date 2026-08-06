"""「エスカレーションのsubsystem内解決」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import (
    CONSULT_COMMENT,
    ESCALATE_INSTRUCTION,
    LOCAL_RESOLUTION,
    SUBSYSTEM_PR_BODY,
    append_user_block,
    approve,
    comments,
    comments_from,
    confirm_labels,
    design_paths,
    drive_until_tester,
    issue,
    label_names,
    me,
    wait_for_user,
)
from tests.e2e.実装対象 import (
    INTEGRATION_MD,
    INTEGRATION_PATH,
    add_worktree,
    seed_subsystem_branch,
    setup_subsystem,
)


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
    """エスカレーション → subsystem レベルの決定 → 設計再開の 1 段折り返しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    login = me(gh_live)
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY, branch_type="docs", artifact="interface",
    )
    # インターフェースだけ確定済みにして、モジュール構成は決定後に作らせる
    seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        include_design=False, design_overrides={INTEGRATION_PATH: INTEGRATION_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])

    # 準備: 候補が全て不適合の相談コメント + 議論中 + assignee=ユーザー（UC の起点）
    consult = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=CONSULT_COMMENT.format(login=login)
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )
    wait_for_user(gh_live, owner, repo, ctx["pr"].number, login)

    # 実行: ユーザーがエスカレーションを指示（議論中 除去 + assignee 外し）
    append_user_block(gh_live, owner, repo, consult, ESCALATE_INSTRUCTION)
    approve(
        gh_live, owner, repo, ctx["pr"].number,
        issue(gh_live, owner, repo, ctx["pr"].number).assignees,
    )

    # 実行: architect のエスカレーション報告を待つ（確認:subsystem-conductor 付与 + 確認:architect 除去）
    def _escalated():
        data = issue(gh_live, owner, repo, ctx["pr"].number)
        names = label_names(data)
        if "確認:subsystem-conductor" not in names or "確認:architect" in names:
            return None
        report = next(
            (c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, "architect")
             if "> to: @subsystem-conductor" in (c.body or "")),
            None,
        )
        return (data, report) if report else None

    escalated, report = wait_until(
        _escalated, timeout_sec=1800, message="architect のエスカレーション報告（確認:subsystem-conductor 付与）"
    )

    # 検証: エスカレーション時点で subsystem PR に確認ラベルが 1 つだけ
    assert confirm_labels(escalated) == ["確認:subsystem-conductor"], (
        f"エスカレーション時点の確認ラベルが 1 つでない: {confirm_labels(escalated)}"
    )

    # 実行: 方針確認 → subsystem レベルの解決案を選択 → 設計再開のゲートに応答して tester まで進める
    history = drive_until_tester(
        gh_live, owner, repo,
        pr_number=ctx["pr"].number,
        faces=[("subsystem_pr", ctx["pr"].number)],
        choices={
            ("subsystem_pr", "確認:subsystem-conductor"): LOCAL_RESOLUTION,
            ("subsystem_pr", "確認:architect"): None,
        },
        wait_until=wait_until,
    )

    # 検証: 方針確認のゲートと、その後の設計確定のゲートを両方通っている
    assert ("subsystem_pr", "確認:subsystem-conductor") in history, (
        f"subsystem-conductor の方針確認ゲートが開かなかった: {history}"
    )
    assert ("subsystem_pr", "確認:architect") in history, (
        f"設計再開後の確認ゲートが開かなかった: {history}"
    )

    # 検証: エスカレーション報告スレッドに決定内容が返信追記され、Resolve 済み
    thread = next(
        (c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id), None
    )
    assert thread is not None, "エスカレーション報告コメントが見つからない"
    assert "> from: @subsystem-conductor" in (thread.body or ""), (
        "スレッドに subsystem-conductor の決定内容が返信追記されていない"
    )
    assert server._is_minimized(report.node_id), "エスカレーション報告スレッドが Resolve されていない"

    # 検証: 決定した方針に沿った設計 Wiki が subsystem ブランチに積まれている
    paths = design_paths(gh_live, owner, repo, ctx["subsystem_branch"])
    assert any(p.startswith("docs/wiki/設計図/モジュール構成/") for p in paths), (
        f"決定後のモジュール構成が commit されていない: {paths}"
    )

    # 検証: 上位（story / epic Issue）へのラベル付与・コメント投稿が発生していない
    for name, number in (("story Issue", ctx["story"].number), ("epic Issue", ctx["epic"].number)):
        upper = issue(gh_live, owner, repo, number)
        assert confirm_labels(upper) == [], f"{name} に確認ラベルが付与されている: {confirm_labels(upper)}"
        assert not comments(gh_live, owner, repo, number), f"{name} にコメントが投稿されている"

    # 検証: subsystem PR は tester へ引き渡され、確認ラベルが多重に残っていない
    final = issue(gh_live, owner, repo, ctx["pr"].number)
    assert confirm_labels(final) == ["確認:tester"], (
        f"確認ラベルが 確認:tester だけになっていない: {confirm_labels(final)}"
    )
    assert "議論中" not in label_names(final), "議論中 が残っている"
