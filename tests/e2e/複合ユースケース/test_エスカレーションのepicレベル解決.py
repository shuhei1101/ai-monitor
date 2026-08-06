"""「エスカレーションのepicレベル解決」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import (
    COMPLEX_SCENARIO_MD,
    COMPLEX_SCENARIO_PATH,
    EPIC_SCENARIO_FIX,
    ESCALATION_REPORT,
    RELAY_UP_FROM_STORY,
    RELAY_UP_FROM_SUBSYSTEM,
    SUBSYSTEM_PR_BODY,
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
    """終端まで遡る 3 段のエスカレーション → epic の決定 → 下位への伝播を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY, branch_type="docs", artifact="interface",
    )
    # 修正対象の複合 UC シナリオを epic ブランチに置く
    commit_file(
        ctx["epic_branch"], COMPLEX_SCENARIO_PATH, COMPLEX_SCENARIO_MD,
        "docs: 複合UC シナリオ（タスク編集から一覧反映）を追加",
    )
    # インターフェースだけ確定済みにして、モジュール構成は決定後に作らせる
    seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        include_design=False, design_overrides={INTEGRATION_PATH: INTEGRATION_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])
    add_worktree(sandbox["local_path"], ctx["epic_branch"])
    epic_body_before = issue(gh_live, owner, repo, ctx["epic"].number).body or ""

    # 準備: architect のエスカレーション報告 → 確認:subsystem-conductor 付与（UC の起点）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ESCALATION_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:subsystem-conductor"]
    )

    # 実行: 3 段の遡上 → epic の決定 → 複合シナリオ修正 → 下位への伝播に応答して tester まで進める
    history = drive_until_tester(
        gh_live, owner, repo,
        pr_number=ctx["pr"].number,
        faces=[
            ("subsystem_pr", ctx["pr"].number),
            ("story_issue", ctx["story"].number),
            ("epic_issue", ctx["epic"].number),
        ],
        choices={
            ("subsystem_pr", "確認:subsystem-conductor"): RELAY_UP_FROM_SUBSYSTEM,
            ("story_issue", "確認:story-conductor"): RELAY_UP_FROM_STORY,
            ("epic_issue", "確認:epic-conductor"): EPIC_SCENARIO_FIX,
            ("subsystem_pr", "確認:architect"): None,
        },
        wait_until=wait_until,
        max_rounds=16,
        timeout_sec=5400,
    )

    # 検証: subsystem → story → epic の 3 段のゲートと、設計再開後のゲートを通っている
    for expected in (
        ("subsystem_pr", "確認:subsystem-conductor"),
        ("story_issue", "確認:story-conductor"),
        ("epic_issue", "確認:epic-conductor"),
        ("subsystem_pr", "確認:architect"),
    ):
        assert expected in history, f"想定したゲートが開かなかった: {expected} / 履歴 {history}"

    # 検証: epic Issue 本文が決定内容で更新されている
    epic_after = issue(gh_live, owner, repo, ctx["epic"].number)
    assert (epic_after.body or "") != epic_body_before, "epic Issue 本文が更新されていない"
    assert "## 横断要件" in (epic_after.body or ""), "epic Issue 本文から横断要件が消えている"

    # 検証: 修正後の複合 UC シナリオが epic ブランチに積まれている
    assert scenario_changed(
        gh_live, owner, repo, ctx["epic_branch"],
        "docs/wiki/設計図/シナリオ/複合ユースケース/", COMPLEX_SCENARIO_MD,
    ), "複合 UC シナリオの修正 commit が積まれていない"

    # 検証: 決定した方針に沿った設計 Wiki が subsystem ブランチに積まれている
    paths = design_paths(gh_live, owner, repo, ctx["subsystem_branch"])
    assert any(p.startswith("docs/wiki/設計図/モジュール構成/") for p in paths), (
        f"決定後のモジュール構成が commit されていない: {paths}"
    )

    # 検証: 各段のエスカレーション関連コメント（報告 / 中継 / 決定通知）が全て Resolve 済み
    assert server._is_minimized(report.node_id), "architect のエスカレーション報告が未 Resolve"
    _assert_escalation_resolved(gh_live, owner, repo,ctx["story"].number, "subsystem-conductor", "story Issue")
    _assert_escalation_resolved(gh_live, owner, repo,ctx["epic"].number, "story-conductor", "epic Issue")
    _assert_escalation_resolved(gh_live, owner, repo,ctx["epic_pr"].number, "epic-conductor", "epic PR")
    _assert_escalation_resolved(gh_live, owner, repo,ctx["epic"].number, "complex-scenario-writer", "epic Issue")
    _assert_escalation_resolved(gh_live, owner, repo,ctx["story"].number, "epic-conductor", "story Issue")
    _assert_escalation_resolved(gh_live, owner, repo,ctx["subsystem"].number, "story-conductor", "subsystem Issue")

    # 検証: subsystem PR は tester へ引き渡され、エスカレーション用の確認ラベルが残っていない
    # （設計再開後の通常フローが付ける確認ラベルは対象外）
    final = issue(gh_live, owner, repo, ctx["pr"].number)
    assert confirm_labels(final) == ["確認:tester"], (
        f"確認ラベルが 確認:tester だけになっていない: {confirm_labels(final)}"
    )
    assert "議論中" not in label_names(final), "subsystem PR に 議論中 が残っている"
    for name, number, label in (
        ("epic Issue", ctx["epic"].number, "確認:epic-conductor"),
        ("epic PR", ctx["epic_pr"].number, "確認:complex-scenario-writer"),
        ("subsystem Issue", ctx["subsystem"].number, "確認:subsystem-conductor"),
    ):
        data = issue(gh_live, owner, repo, number)
        assert label not in label_names(data), f"{name} に {label} が残っている"
