"""「epic要件確定」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.epic起動 import (
    EPIC_SECTIONS,
    assert_comments_resolved,
    assert_linked_issue_only_body,
    drive_requirements,
)
from tests.e2e.ゲート応答 import open_prs_for
from tests.e2e.システム import watch_numbers
from tests.e2e.エスカレーション import comments

INTAKE_TITLE = "タスク期限のメール通知機能"
INTAKE_BODY = """タスクの期限が近づいたらメールで通知する機能を追加したいです。

- 通知の on/off はユーザー設定で切り替えたい
- 通知タイミング（1 日前 / 1 時間前）も選べるようにしたい
"""
EPIC_TITLE = "タスク期限のメール通知機能"


def _assert_requirements(gh_live, owner, repo, epic_number: int, first) -> None:
    """初回ターンの成果（本文 5 セクション・対応 story 未起票・確認質問コメント）を検証する。"""
    body = (first.body or "").replace("\r\n", "\n")
    for section in EPIC_SECTIONS:
        assert section in body, f"本文に {section} がない"
    assert "未起票" in body
    assert comments(gh_live, owner, repo, epic_number), "完了報告・確認質問コメントが投稿されていない"


def test_normal_no_poc_no_ui(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path):
    """epic 本文確定 → 承認 → epic Draft PR 作成 + complex-scenario-writer 引き継ぎを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 不要・画面変更なしと回答）
    first, _ = drive_requirements(
        gh_live, owner, repo, wait_until, epic.number,
        answer_body="A（PoC 不要）/ A（画面変更なし）でお願いします。",
    )
    _assert_requirements(gh_live, owner, repo, epic.number, first)

    # 検証: epic Draft PR（base=master・本文は 紐づく Issue のみ）が 1 件作成され 確認:complex-scenario-writer 付与
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True
    assert pr.base.ref == "master"
    assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:complex-scenario-writer" in pr_labels

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number)

    # 検証: エージェント投稿の自分宛コメントが全て Resolve 済み
    assert_comments_resolved(gh_live, owner, repo, epic.number)


def test_normal_no_poc_with_ui(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path):
    """epic 本文確定 → 承認 → epic Draft PR 作成 + mock-designer 引き継ぎと指示コメントを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 不要・画面変更ありと回答）
    first, _ = drive_requirements(
        gh_live, owner, repo, wait_until, epic.number,
        answer_body="A（PoC 不要）/ B（画面変更あり: 通知設定画面を新規作成）でお願いします。",
    )
    _assert_requirements(gh_live, owner, repo, epic.number, first)

    # 検証: epic Draft PR（base=master・本文は 紐づく Issue のみ）が 1 件作成され 確認:mock-designer 付与
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True
    assert pr.base.ref == "master"
    assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:mock-designer" in pr_labels

    # 検証: PR に @mock-designer 宛の指示コメントが未 Resolve で投稿されている
    directed = [c for c in comments(gh_live, owner, repo, pr.number) if "> to: @mock-designer" in c.body]
    assert directed, "@mock-designer 宛の指示コメントが投稿されていない"
    assert not server._is_minimized(directed[-1].node_id), "指示コメントが Resolve されてしまっている"

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number)


def test_normal_poc_required(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, e2e_state_path):
    """epic 本文確定 → 承認 → PoC Draft PR 作成 + epic-poc-runner 引き継ぎ（epic Draft PR なし）を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 必要と回答）
    first, _ = drive_requirements(
        gh_live, owner, repo, wait_until, epic.number,
        answer_body="B（PoC 必要: メール一斉送信のスループット検証）/ A（画面変更なし）でお願いします。",
    )
    _assert_requirements(gh_live, owner, repo, epic.number, first)

    # 検証: PoC Draft PR のみが 1 件作成され（epic Draft PR は作成されない）確認:epic-poc-runner 付与
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"PoC Draft PR のみの 1 件でない: {[(pr.number, pr.title) for pr in prs]}"
    pr = prs[0]
    assert pr.title.startswith("PoC:"), f"タイトルが PoC: 始まりでない: {pr.title}"
    assert f"#{epic.number}" in pr.title
    assert pr.draft is True
    assert pr.base.ref == "master"
    assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:epic-poc-runner" in pr_labels

    # 検証: PR に @epic-poc-runner 宛の指示コメントが未 Resolve で投稿されている
    directed = [c for c in comments(gh_live, owner, repo, pr.number) if "> to: @epic-poc-runner" in c.body]
    assert directed, "@epic-poc-runner 宛の指示コメントが投稿されていない"
    assert not server._is_minimized(directed[-1].node_id), "指示コメントが Resolve されてしまっている"

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number)
