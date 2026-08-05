"""「Issue起票からepic起動まで」の E2E テスト。"""
from __future__ import annotations

from tests.e2e.epic起動 import EPIC_SECTIONS, assert_comments_resolved, drive_requirements
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


def _open_prs(gh_live, owner, repo, *, base: str | None = None) -> list:
    """open PR を返す（base 指定時はその base のものだけ）。"""
    kwargs = {"base": base} if base else {}
    return list(
        gh_live.rest.pulls.list(
            owner=owner, repo=repo, state="open", per_page=100, **kwargs
        ).parsed_data
    )


def test_normal(monitor, gh_live, repo_ctx, intake_issue_factory, wait_until, e2e_state_path):
    """intake の epic 判定 → epic PR 作成 → 要件確定 → 成果物 PR までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: ユーザー起票の intake Issue（確認ラベル付き・assignee なし）
    intake = intake_issue_factory(title=INTAKE_TITLE, body=INTAKE_BODY)

    # 実行: 分解判定（初回）の完了（分解案の提示 + 待機）を待つ
    def _triage_done():
        data = issue(gh_live, owner, repo, intake.number)
        return data if waiting_for_user(data) else None

    triaged = wait_until(
        _triage_done, timeout_sec=1800, message="分解判定（初回）の完了（議論中 + assignee）"
    )

    # 検証: intake Issue に集約ラベルと分解案コメントが揃い、本文はユーザー起票時のまま
    names = label_names(triaged)
    assert "layer:intake" in names, f"layer:intake がない: {sorted(names)}"
    assert any(name.startswith("type:") for name in names), f"type:* がない: {sorted(names)}"
    assert comments(gh_live, owner, repo, intake.number), "分解案コメントが投稿されていない"
    assert (triaged.body or "").replace("\r\n", "\n") == INTAKE_BODY, "intake 本文が書き換わっている"

    # 実行: ユーザー承認（議論中 除去 + assignee 外し）
    approve(gh_live, owner, repo, intake.number, triaged.assignees)

    # 実行: 子PR作成（完了処理）の完了を待つ（master 直下に epic PR が生える）
    def _epic_pr_created():
        data = issue(gh_live, owner, repo, intake.number)
        if any(name.startswith("確認:") for name in label_names(data)):
            return None
        children = [
            pr for pr in _open_prs(gh_live, owner, repo, base="master")
            if f"#{intake.number}" in (pr.body or "")
        ]
        return children or None

    children = wait_until(
        _epic_pr_created, timeout_sec=1800, message="子PR作成（完了処理）の完了（epic PR の作成）"
    )

    # 検証: epic PR 1 件に分解され layer:epic + type:* + 確認:epic-conductor が付与されている
    assert len(children) == 1, f"epic PR 1 件に分解されていない: {[pr.title for pr in children]}"
    epic_pr = children[0]
    assert epic_pr.draft, "epic PR が Draft でない"
    epic_labels = label_names(issue(gh_live, owner, repo, epic_pr.number))
    assert "layer:epic" in epic_labels, f"#{epic_pr.number} に layer:epic がない: {sorted(epic_labels)}"
    assert any(name.startswith("type:") for name in epic_labels), (
        f"#{epic_pr.number} に type:* がない: {sorted(epic_labels)}"
    )
    assert "確認:epic-conductor" in epic_labels, (
        f"#{epic_pr.number} に 確認:epic-conductor がない: {sorted(epic_labels)}"
    )

    # 実行: epic 要件確定をユーザー役として進める（PoC 不要・画面変更なしと回答）
    _, completed = drive_requirements(
        gh_live, owner, repo, wait_until, epic_pr.number, answer_body=REQUIREMENTS_ANSWER
    )

    # 検証: epic PR 本文に必須セクションが揃い 対応 story 列が未作成のまま
    epic_body = (completed.body or "").replace("\r\n", "\n")
    for section in EPIC_SECTIONS:
        assert section in epic_body, f"epic PR 本文に {section} がない"
    assert "未作成" in epic_body, "ユースケース一覧の 対応 story 列が未作成でない"

    # 検証: 複合 UC シナリオの成果物 PR（base=epic ブランチ）が 1 件作られ次担当へ渡っている
    artifacts = _open_prs(gh_live, owner, repo, base=epic_pr.head.ref)
    assert len(artifacts) == 1, f"成果物 PR が 1 件でない: {[pr.number for pr in artifacts]}"
    artifact = artifacts[0]
    assert artifact.draft, "成果物 PR が Draft でない"
    artifact_labels = label_names(issue(gh_live, owner, repo, artifact.number))
    assert "確認:complex-scenario-writer" in artifact_labels, (
        f"成果物 PR に 確認:complex-scenario-writer がない: {sorted(artifact_labels)}"
    )

    # 検証: 作成した PR の番号が epic-conductor セッションの監視面（モニターの台帳）に登録されている
    watched = watch_numbers(e2e_state_path, "epic-conductor", epic_pr.number)
    assert artifact.number in watched, f"成果物 PR が監視面に登録されていない: {watched}"

    # 検証: intake は open のまま確認ラベルが残っていない
    intake_now = issue(gh_live, owner, repo, intake.number)
    assert intake_now.state == "open", "intake Issue が close されている"
    assert not [name for name in label_names(intake_now) if name.startswith("確認:")], (
        "intake Issue に確認ラベルが残っている"
    )

    # 検証: epic PR の確認ラベルが次担当へ渡り、自分の確認ラベルは残っていない
    assert "確認:epic-conductor" not in label_names(completed), (
        "epic PR に 確認:epic-conductor が残っている"
    )

    # 検証: 両面の自分宛コメントが全て Resolve 済み
    assert_comments_resolved(gh_live, owner, repo, intake.number)
    assert_comments_resolved(gh_live, owner, repo, epic_pr.number)
