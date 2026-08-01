"""「Issue起票からepic起動まで」の E2E テスト。"""
from __future__ import annotations

from tests.e2e.epic起動 import (
    EPIC_SECTIONS,
    assert_comments_resolved,
    assert_task_list_body,
    drive_requirements,
)
from tests.e2e.ゲート応答 import open_prs_for
from tests.e2e.システム import watch_numbers
from tests.e2e.エスカレーション import approve, comments, issue, label_names, waiting_for_user

INTAKE_TITLE = "タスク期限のメール通知機能"
INTAKE_BODY = """タスクの期限が近づいたらメールで通知する機能を追加したいです。

- 通知の on/off はユーザー設定で切り替えたい
- 通知タイミング（1 日前 / 1 時間前）も選べるようにしたい

この Issue に含める作業はこの通知機能だけで、他の変更は不要です。
"""

# 分解の結末を epic 1 件へ、要件確定の分岐を PoC 不要・画面変更なしへ決定的に誘導する回答
REQUIREMENTS_ANSWER = "A（PoC 不要）/ A（画面変更なし）でお願いします。"


def test_normal(monitor, gh_live, repo_ctx, intake_issue_factory, wait_until, e2e_state_path):
    """intake の epic 判定 → epic-conductor の起動 → epic Draft PR 作成までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: ユーザー起票の intake Issue（確認ラベル付き・assignee なし）
    intake = intake_issue_factory(title=INTAKE_TITLE, body=INTAKE_BODY)

    # 実行: 分解判定（初回）の完了（サブ Issue 案の提示 + 待機）を待つ
    def _triage_done():
        data = issue(gh_live, owner, repo, intake.number)
        return data if waiting_for_user(data) else None

    triaged = wait_until(_triage_done, timeout_sec=1800, message="分解判定（初回）の完了（議論中 + assignee）")

    # 検証: intake Issue に集約ラベルとサブ Issue 案コメントが揃い、本文はユーザー起票時のまま
    names = label_names(triaged)
    assert "layer:intake" in names, f"layer:intake がない: {sorted(names)}"
    assert any(name.startswith("type:") for name in names), f"type:* がない: {sorted(names)}"
    assert comments(gh_live, owner, repo, intake.number), "サブ Issue 案コメントが投稿されていない"
    assert (triaged.body or "").replace("\r\n", "\n") == INTAKE_BODY, "intake 本文が書き換わっている"

    # 実行: ユーザー承認（議論中 除去 + assignee 外し）
    approve(gh_live, owner, repo, intake.number, triaged.assignees)

    # 実行: サブIssue起票（完了処理）の完了を待つ
    def _subissues_created():
        data = issue(gh_live, owner, repo, intake.number)
        if any(name.startswith("確認:") for name in label_names(data)):
            return None
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=intake.number
        ).parsed_data
        return subs or None

    subs = wait_until(_subissues_created, timeout_sec=1800, message="サブIssue起票（完了処理）の完了")

    # 検証: epic 1 件に分解され layer:epic + type:* + 確認:epic-conductor が付与されている（検証対象の繋ぎ目）
    assert len(subs) == 1, f"epic 1 件に分解されていない: {[s.title for s in subs]}"
    epic = subs[0]
    epic_labels = {label.name for label in epic.labels}
    assert "layer:epic" in epic_labels, f"#{epic.number} に layer:epic がない: {sorted(epic_labels)}"
    assert any(name.startswith("type:") for name in epic_labels), (
        f"#{epic.number} に type:* がない: {sorted(epic_labels)}"
    )
    assert "確認:epic-conductor" in epic_labels, (
        f"#{epic.number} に 確認:epic-conductor がない: {sorted(epic_labels)}"
    )

    # 実行: epic 要件確定をユーザー役として進める（PoC 不要・画面変更なしと回答）
    _, completed = drive_requirements(
        gh_live, owner, repo, wait_until, epic.number, answer_body=REQUIREMENTS_ANSWER
    )

    # 検証: epic Issue 本文に 5 セクションが揃い 対応 story 列が未起票のまま
    epic_body = (completed.body or "").replace("\r\n", "\n")
    for section in EPIC_SECTIONS:
        assert section in epic_body, f"epic 本文に {section} がない"
    assert "未起票" in epic_body, "ユースケース一覧の 対応 story 列が未起票でない"

    # 検証: epic Draft PR（base=master・本文は 紐づく Issue のみ）が 1 件作成され 確認:complex-scenario-writer 付与
    prs = open_prs_for(gh_live, owner, repo, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True, "epic PR が Draft でない"
    assert pr.base.ref == "master", f"epic PR の base が master でない: {pr.base.ref}"
    assert_task_list_body(pr)
    assert "確認:complex-scenario-writer" in {label.name for label in pr.labels}, (
        f"epic PR に 確認:complex-scenario-writer がない: {sorted(label.name for label in pr.labels)}"
    )

    # 検証: 作成した PR の番号が epic-conductor セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in watch_numbers(e2e_state_path, "epic-conductor", epic.number), (
        "epic Draft PR が監視面に登録されていない"
    )

    # 検証: intake / epic とも open のまま確認ラベルが残っていない
    intake_now = issue(gh_live, owner, repo, intake.number)
    assert intake_now.state == "open", "intake Issue が close されている"
    assert not [name for name in label_names(intake_now) if name.startswith("確認:")], (
        "intake Issue に確認ラベルが残っている"
    )
    assert completed.state == "open", "epic Issue が close されている"
    assert not [name for name in label_names(completed) if name.startswith("確認:")], (
        "epic Issue に確認ラベルが残っている"
    )

    # 検証: 両 Issue の自分宛コメントが全て Resolve 済み
    assert_comments_resolved(gh_live, owner, repo, intake.number)
    assert_comments_resolved(gh_live, owner, repo, epic.number)
