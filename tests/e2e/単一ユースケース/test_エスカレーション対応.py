"""「エスカレーション対応」の E2E テスト。

図は subsystem レベルで代表されるが、シナリオ修正を伴う 2 本は story レベルの実体なので
それぞれのレベルで実行する。
"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import (
    ESCALATION_REPORT,
    SUBSYSTEM_PR_BODY,
    append_user_block,
    approve,
    comments,
    comments_from,
    issue,
    label_names,
    waiting_for_user,
)
from tests.e2e.実装対象 import (
    INTEGRATION_MD,
    INTEGRATION_PATH,
    SCENARIO_MD,
    SCENARIO_PATH,
    add_worktree,
    seed_subsystem_branch,
    setup_subsystem,
)

LOCAL_CHOICE = (
    "自レイヤーの解決案でお願いします。subsystem 内で代替手段を検討して設計を進めてください。"
)
RELAY_CHOICE = (
    "上位への中継でお願いします。subsystem レイヤーでは決められないので親 story へ渡してください。"
)
STORY_SCENARIO_CHOICE = (
    "単一ユースケースシナリオ「タスク編集」を非同期の結末へ変更する案でお願いします。"
    "シナリオの修正から進めてください。"
)

STORY_ESCALATION_REPORT = """> from: @subsystem-conductor
> to: @story-conductor

配下の subsystem では解決できない論点が上がってきました。

経緯:
- 単一ユースケースシナリオ「タスク編集」は「保存の完了を待って一覧へ戻る」同期の流れを前提にしている
- 更新の確定は外部の承認基盤への連携が必須で、応答が非同期でしか返らない
- subsystem 内の待ち合わせ実装は UC の応答時間の前提を満たせない

論点:
- 同期前提のシナリオを維持するのか、非同期の結末に変えるのかを決められない

------
"""

SCENARIO_FIX_DONE = """> from: @single-scenario-writer
> to: @story-conductor

エスカレーション対応で指示された単一ユースケースシナリオの修正が完了しました。

| ファイル | 内容 |
| --- | --- |
| `設計図/シナリオ/単一ユースケース/タスク編集.md` | 保存完了を待たずに受付完了を表示する非同期の結末へ変更 |

修正はユーザー確認を経て確定済みです。

------
"""


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory):
    """セットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "subsystem_issue_factory": subsystem_issue_factory,
    }


def _setup_escalated(gh_live, owner, repo, factories, commit_file, sandbox):
    """architect のエスカレーション報告が上がった状態の subsystem PR 一式を用意する。"""
    ctx = setup_subsystem(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["draft_pr_factory"],
        factories["story_issue_factory"], factories["subsystem_issue_factory"], commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        include_design=False, design_overrides={INTEGRATION_PATH: INTEGRATION_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ESCALATION_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:subsystem-conductor"]
    )
    return ctx, report


def _wait_gate(gh_live, owner, repo, number, wait_until, *, message):
    """対応方針案の確認ゲート（議論中 + assignee）を待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, number)
        return data if waiting_for_user(data) else None

    return wait_until(_done, timeout_sec=2400, message=message)


def test_normal_when_ask(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """エスカレーション報告を受けて選択肢付きの方針案を提示することを確認する（正常系・方針確認）。"""
    owner, repo = repo_ctx
    ctx, report = _setup_escalated(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, sandbox,
    )

    data = _wait_gate(gh_live, owner, repo, ctx["pr"].number, wait_until, message="対応方針案の確認ゲート")

    # 検証: 方針案コメントが投稿され、確認ラベルは保持されたまま
    proposals = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, "subsystem-conductor")
    ]
    assert proposals, "対応方針案コメントが投稿されていない"
    assert "確認:subsystem-conductor" in label_names(data), (
        f"確認:subsystem-conductor が保持されていない: {sorted(label_names(data))}"
    )
    assert not server._is_minimized(report.node_id), (
        "エスカレーション報告が Resolve されている（選択後の実行で Resolve する）"
    )

    # 検証: ユーザーの選択前に上位 Issue へ上げていない
    for number in (ctx["story"].number, ctx["epic"].number):
        upper = issue(gh_live, owner, repo, number)
        assert not [n for n in label_names(upper) if n.startswith("確認:")], (
            f"#{number} に確認ラベルが付与されている"
        )
        assert not comments(gh_live, owner, repo, number), f"#{number} にコメントが投稿されている"


def test_normal_when_local(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """自レイヤーの解決案が選ばれたときの architect への再開指示を確認する（正常系・自レイヤーで解決）。"""
    owner, repo = repo_ctx
    ctx, report = _setup_escalated(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, sandbox,
    )
    data = _wait_gate(gh_live, owner, repo, ctx["pr"].number, wait_until, message="対応方針案の確認ゲート")

    # 実行: 自レイヤーの解決案を選択（議論中 除去 + assignee 外し）
    append_user_block(gh_live, owner, repo, comments(gh_live, owner, repo, ctx["pr"].number)[-1], LOCAL_CHOICE)
    approve(gh_live, owner, repo, ctx["pr"].number, data.assignees)

    # 実行: architect への再開指示を待つ
    def _resumed():
        pr_now = issue(gh_live, owner, repo, ctx["pr"].number)
        names = label_names(pr_now)
        return pr_now if "確認:architect" in names and "確認:subsystem-conductor" not in names else None

    wait_until(_resumed, timeout_sec=2400, message="architect への再開指示（確認:architect 付与）")

    # 検証: エスカレーション報告スレッドに決定内容が返信追記され、Resolve 済み
    thread = next(c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id)
    assert "> from: @subsystem-conductor" in (thread.body or ""), "決定内容が返信追記されていない"
    assert server._is_minimized(report.node_id), "エスカレーション報告が未 Resolve"

    # 検証: 上位 Issue へのラベル付与・コメント投稿が発生していない
    for number in (ctx["story"].number, ctx["epic"].number):
        upper = issue(gh_live, owner, repo, number)
        assert not [n for n in label_names(upper) if n.startswith("確認:")], (
            f"#{number} に確認ラベルが付与されている"
        )


def test_normal_when_relay(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """上位への中継が選ばれたときの親 story への中継を確認する（正常系・上位への中継）。"""
    owner, repo = repo_ctx
    ctx, report = _setup_escalated(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, sandbox,
    )
    data = _wait_gate(gh_live, owner, repo, ctx["pr"].number, wait_until, message="対応方針案の確認ゲート")

    # 実行: 上位への中継を選択（議論中 除去 + assignee 外し）
    append_user_block(gh_live, owner, repo, comments(gh_live, owner, repo, ctx["pr"].number)[-1], RELAY_CHOICE)
    approve(gh_live, owner, repo, ctx["pr"].number, data.assignees)

    # 実行: 親 story への中継を待つ
    def _relayed():
        story_now = issue(gh_live, owner, repo, ctx["story"].number)
        if "確認:story-conductor" not in label_names(story_now):
            return None
        relayed = comments_from(gh_live, owner, repo, ctx["story"].number, "subsystem-conductor")
        if not relayed:
            return None
        pr_now = issue(gh_live, owner, repo, ctx["pr"].number)
        return (pr_now, relayed[-1]) if not [
            n for n in label_names(pr_now) if n.startswith("確認:")
        ] else None

    pr_now, relayed = wait_until(_relayed, timeout_sec=2400, message="親 story への中継")

    # 検証: 中継コメントが @story-conductor 宛で未解決、subsystem PR は保留（確認ラベルなし）
    assert "> to: @story-conductor" in (relayed.body or ""), "中継コメントの宛先が違う"
    assert not server._is_minimized(relayed.node_id), "中継コメントが Resolve されている"
    assert server._is_minimized(report.node_id), "エスカレーション報告が未 Resolve"

    # 検証: レイヤーを飛び越して epic Issue へ上げていない
    epic_now = issue(gh_live, owner, repo, ctx["epic"].number)
    assert not [n for n in label_names(epic_now) if n.startswith("確認:")], (
        "epic Issue に確認ラベルが付与されている（1 段ずつ遡上するはず）"
    )
    assert not comments(gh_live, owner, repo, ctx["epic"].number), "epic Issue にコメントが投稿されている"


def test_normal_when_receive_decision(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """上位から降りてきた決定を受領して architect へ再開指示することを確認する（正常系・上位の決定の受領）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        include_design=False, design_overrides={INTEGRATION_PATH: INTEGRATION_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])

    # 準備: 上位（story-conductor）の決定コメント → 確認ラベル付与（起動トリガー）
    decision = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number,
        body=(
            "> from: @story-conductor\n> to: @subsystem-conductor\n\n"
            "エスカレーションいただいた論点について方針が決まりました。\n\n"
            "決定: 単一ユースケースシナリオを非同期の結末へ変更しました。"
            "更新は受付完了を返し、確定は後続の通知で伝える方式にします。\n\n"
            "この方針で subsystem の設計を再開してください。"
        ),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:subsystem-conductor"]
    )

    # 実行: architect への再開指示を待つ
    def _resumed():
        pr_now = issue(gh_live, owner, repo, ctx["pr"].number)
        names = label_names(pr_now)
        if "確認:architect" not in names or "確認:subsystem-conductor" in names:
            return None
        instructions = [
            c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, "subsystem-conductor")
        ]
        return (pr_now, instructions[-1]) if instructions else None

    pr_now, instruction = wait_until(
        _resumed, timeout_sec=2400, message="決定の受領と architect への再開指示"
    )

    # 検証: 決定コメントのスレッドに受領が返信追記され、Resolve 済み
    thread = next(c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == decision.node_id)
    assert "> from: @subsystem-conductor" in (thread.body or ""), "受領が返信追記されていない"
    assert server._is_minimized(decision.node_id), "上位の決定コメントが未 Resolve"

    # 検証: 再開指示が @architect 宛で未解決
    assert "> to: @architect" in (instruction.body or ""), "再開指示の宛先が architect でない"
    assert not server._is_minimized(instruction.node_id), "再開指示が Resolve されている"


def test_normal_when_scenario_fix(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ変更を伴う解決案が選ばれたときの writer への修正指示を確認する（正常系・シナリオ修正を伴う解決）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )

    # 準備: story Issue に subsystem-conductor のエスカレーション報告 + 方針確認ゲートを再現
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["story"].number, body=STORY_ESCALATION_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["story"].number, labels=["確認:story-conductor"]
    )
    data = _wait_gate(gh_live, owner, repo, ctx["story"].number, wait_until, message="story レベルの方針確認ゲート")

    # 実行: シナリオ変更を伴う解決案を選択（議論中 除去 + assignee 外し）
    append_user_block(
        gh_live, owner, repo, comments(gh_live, owner, repo, ctx["story"].number)[-1], STORY_SCENARIO_CHOICE
    )
    approve(gh_live, owner, repo, ctx["story"].number, data.assignees)

    # 実行: story PR への修正指示を待つ
    def _instructed():
        story_now = issue(gh_live, owner, repo, ctx["story"].number)
        if "確認:story-conductor" in label_names(story_now):
            return None
        pr_now = issue(gh_live, owner, repo, ctx["story_pr"].number)
        if "確認:single-scenario-writer" not in label_names(pr_now):
            return None
        instructions = comments_from(gh_live, owner, repo, ctx["story_pr"].number, "story-conductor")
        return (story_now, instructions[-1]) if instructions else None

    story_now, instruction = wait_until(
        _instructed, timeout_sec=2400, message="story PR へのシナリオ修正指示"
    )

    # 検証: 修正指示が @single-scenario-writer 宛で未解決
    assert "> to: @single-scenario-writer" in (instruction.body or ""), "修正指示の宛先が違う"
    assert not server._is_minimized(instruction.node_id), "修正指示が Resolve されている"
    assert server._is_minimized(report.node_id), "エスカレーション報告が未 Resolve"

    # 検証: シナリオ確定前に下位 subsystem へ降ろしていない
    sub_now = issue(gh_live, owner, repo, ctx["subsystem"].number)
    assert not [n for n in label_names(sub_now) if n.startswith("確認:")], (
        "subsystem Issue に確認ラベルが付与されている（シナリオ確定前に降ろさない）"
    )


def test_normal_when_notify_decision(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """シナリオ修正完了を受けて発生元 subsystem へ決定を通知することを確認する（正常系・修正完了後の決定通知）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    # 準備: 修正済みのシナリオを story ブランチへ積む
    commit_file(
        ctx["story_branch"], SCENARIO_PATH,
        SCENARIO_MD.replace(
            "  FE-->>U: 一覧へ戻り 完了トースト表示",
            "  FE-->>U: 一覧へ戻り 受付完了トースト表示",
        ).replace(
            "- 一覧に編集後の内容が表示されている",
            "- 一覧に受付完了の状態が表示されている",
        ),
        "docs: 単一UC シナリオを非同期の結末へ修正",
    )
    # 準備: single-scenario-writer のシナリオ修正完了報告 → 確認ラベル付与（起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["story"].number, body=SCENARIO_FIX_DONE
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["story"].number, labels=["確認:story-conductor"]
    )

    # 実行: 発生元 subsystem への決定通知を待つ
    def _notified():
        story_now = issue(gh_live, owner, repo, ctx["story"].number)
        if "確認:story-conductor" in label_names(story_now):
            return None
        sub_now = issue(gh_live, owner, repo, ctx["subsystem"].number)
        if "確認:subsystem-conductor" not in label_names(sub_now):
            return None
        notices = comments_from(gh_live, owner, repo, ctx["subsystem"].number, "story-conductor")
        return notices[-1] if notices else None

    notice = wait_until(_notified, timeout_sec=2400, message="発生元 subsystem への決定通知")

    # 検証: 決定通知が @subsystem-conductor 宛で未解決、完了報告は Resolve 済み
    assert "> to: @subsystem-conductor" in (notice.body or ""), "決定通知の宛先が違う"
    assert not server._is_minimized(notice.node_id), "決定通知が Resolve されている"
    assert server._is_minimized(report.node_id), "シナリオ修正完了報告が未 Resolve"
