"""「エスカレーションのstoryレベル解決」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import (
    ESCALATION_REPORT,
    RELAY_UP_FROM_SUBSYSTEM,
    STORY_SCENARIO_FIX,
    SUBSYSTEM_PR_BODY,
    comments,
    comments_from,
    confirm_labels,
    design_paths,
    drive_until_tester,
    issue,
    label_names,
    scenario_changed,
)
from tests.e2e.実装対象 import (
    INTEGRATION_MD,
    INTEGRATION_PATH,
    SCENARIO_MD,
    add_worktree,
    seed_subsystem_branch,
    setup_subsystem,
)


def _assert_escalation_resolved(gh_live, owner, repo, number, sender, label) -> None:
    """エスカレーション連鎖のコメント（その面への当該エージェントの初回投稿）が Resolve 済みか検証する。

    設計再開後の通常フロー（インターフェース確定報告 等）は同じ宛先で後から積まれるので、
    連鎖の起点になった 1 件だけを対象にする。
    """
    targets = comments_from(gh_live, owner, repo, number, sender)
    assert targets, f"{label} に {sender} のコメントがない"
    first = targets[0]
    assert server._is_minimized(first.node_id), (
        f"{label} の {sender} のエスカレーション関連コメントが未 Resolve: {first.html_url}"
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
    """2 段のエスカレーション → story レベルの決定 → シナリオ修正 → 設計再開を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
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
    add_worktree(sandbox["local_path"], ctx["story_branch"])
    story_body_before = issue(gh_live, owner, repo, ctx["story"].number).body or ""

    # 準備: architect のエスカレーション報告 → 確認:subsystem-conductor 付与（UC の起点）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ESCALATION_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:subsystem-conductor"]
    )

    # 実行: 中継 → story レベルの決定 → シナリオ修正 → 設計再開のゲートに応答して tester まで進める
    history = drive_until_tester(
        gh_live, owner, repo,
        pr_number=ctx["pr"].number,
        faces=[("subsystem_pr", ctx["pr"].number), ("story_issue", ctx["story"].number)],
        choices={
            ("subsystem_pr", "確認:subsystem-conductor"): RELAY_UP_FROM_SUBSYSTEM,
            ("story_issue", "確認:story-conductor"): STORY_SCENARIO_FIX,
            ("subsystem_pr", "確認:architect"): None,
        },
        wait_until=wait_until,
        timeout_sec=5400,
    )

    # 検証: subsystem → story の 2 段のゲートと、設計再開後のゲートを通っている
    for expected in (
        ("subsystem_pr", "確認:subsystem-conductor"),
        ("story_issue", "確認:story-conductor"),
        ("subsystem_pr", "確認:architect"),
    ):
        assert expected in history, f"想定したゲートが開かなかった: {expected} / 履歴 {history}"

    # 検証: 修正後の単一 UC シナリオが story ブランチに積まれている
    assert scenario_changed(
        gh_live, owner, repo, ctx["story_branch"],
        "docs/wiki/設計図/シナリオ/単一ユースケース/", SCENARIO_MD,
    ), "単一 UC シナリオの修正 commit が積まれていない"

    # 検証: story Issue 本文のユースケース要件が決定内容で更新されている
    story_after = issue(gh_live, owner, repo, ctx["story"].number)
    assert (story_after.body or "") != story_body_before, "story Issue 本文が更新されていない"
    assert "## ユースケース要件" in (story_after.body or ""), "story Issue 本文からユースケース要件が消えている"

    # 検証: 決定した方針に沿った設計 Wiki が subsystem ブランチに積まれている
    paths = design_paths(gh_live, owner, repo, ctx["subsystem_branch"])
    assert any(p.startswith("docs/wiki/設計図/モジュール構成/") for p in paths), (
        f"決定後のモジュール構成が commit されていない: {paths}"
    )

    # 検証: epic Issue へのラベル付与・コメント投稿が発生していない（2 段で折り返している）
    epic = issue(gh_live, owner, repo, ctx["epic"].number)
    assert confirm_labels(epic) == [], f"epic Issue に確認ラベルが付与されている: {confirm_labels(epic)}"
    assert not comments(gh_live, owner, repo, ctx["epic"].number), "epic Issue にコメントが投稿されている"

    # 検証: 各段のエスカレーション関連コメントが全て Resolve 済み
    assert server._is_minimized(report.node_id), "architect のエスカレーション報告が未 Resolve"
    _assert_escalation_resolved(gh_live, owner, repo,ctx["story"].number, "subsystem-conductor", "story Issue")
    _assert_escalation_resolved(gh_live, owner, repo,ctx["story"].number, "single-scenario-writer", "story Issue")
    _assert_escalation_resolved(gh_live, owner, repo,ctx["story_pr"].number, "story-conductor", "story PR")
    _assert_escalation_resolved(gh_live, owner, repo,ctx["subsystem"].number, "story-conductor", "subsystem Issue")

    # 検証: subsystem PR は tester へ引き渡され、確認ラベルが余分に残っていない
    final = issue(gh_live, owner, repo, ctx["pr"].number)
    assert confirm_labels(final) == ["確認:tester"], (
        f"確認ラベルが 確認:tester だけになっていない: {confirm_labels(final)}"
    )
    assert "議論中" not in label_names(final), "subsystem PR に 議論中 が残っている"
    # 設計再開後の通常フローが付ける確認ラベルは対象外なので、エスカレーション用のものだけを見る
    for name, number, label in (
        ("story PR", ctx["story_pr"].number, "確認:single-scenario-writer"),
        ("subsystem Issue", ctx["subsystem"].number, "確認:subsystem-conductor"),
    ):
        data = issue(gh_live, owner, repo, number)
        assert label not in label_names(data), f"{name} に {label} が残っている"
