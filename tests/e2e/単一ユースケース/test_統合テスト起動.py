"""「統合テスト起動」の E2E テスト（epic レベルの読み替えで検証）。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

import server

INTAKE_TITLE = "タスク期限のメール通知機能"
INTAKE_BODY = "タスクの期限が近づいたらメールで通知する機能を追加したいです。"
EPIC_TITLE = "タスク期限のメール通知機能"

PR_BODY = """## 紐づく Issue

- #{epic_number}
"""

STORY_DONE_REPORT = """> from: @story-conductor
> to: @epic-conductor

story #{story_number} のマージが完了しました（story PR は epic ブランチへ merged 済み・story Issue は自動 close）。
"""

FAIL_REPORT = """> from: @complex-scenario-writer
> to: @epic-conductor

複合 UC テストが fail しました。トリアージの結果、実装側の問題です。

- fail した UC: 期限通知メールの受信
- fail 内容: 通知メールの送信時刻が期限の 24 時間前を超過している（story #{story_number} の実装範囲）
- 修正方針案: 通知スケジューラの起動条件を修正する
"""


def _make_story(gh_live, repo_ctx, epic_number: int, title: str, *, closed: bool) -> object:
    """epic の Sub-issue として story Issue を作成する（closed=True なら completed でクローズ）。"""
    owner, repo = repo_ctx
    story = gh_live.rest.issues.create(
        owner=owner, repo=repo, title=title, body="", labels=["layer:story"]
    ).parsed_data
    gh_live.rest.issues.add_sub_issue(owner=owner, repo=repo, issue_number=epic_number, sub_issue_id=story.id)
    if closed:
        gh_live.rest.issues.update(
            owner=owner, repo=repo, issue_number=story.number, state="closed", state_reason="completed"
        )
    return story


def test_normal_delegate(monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, epic_body, wait_until):
    """全子 story 完了の確認 → complex-scenario-writer への統合テスト委任を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: 要件確定済み epic + closed の子 story + epic Draft PR（確認ラベルは最後に付ける）
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=epic_body, epic_labels=["layer:epic"]
    )
    story = _make_story(gh_live, repo_ctx, epic.number, "期限通知メールの受信", closed=True)
    pr = epic_pr_factory(
        branch=f"feat/epic/togo-delegate-{epic.number}", title=EPIC_TITLE, body=PR_BODY.format(epic_number=epic.number)
    )
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic.number, body=STORY_DONE_REPORT.format(story_number=story.number)
    ).parsed_data
    gh_live.rest.issues.add_labels(owner=owner, repo=repo, issue_number=epic.number, labels=["確認:epic-conductor"])

    # 実行: モニターの polling 検知 → 統合テスト委任の完了を待つ
    def _delegated():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=pr.number).parsed_data
        labels = {label.name for label in data.labels}
        return data if "確認:complex-scenario-writer" in labels else None

    wait_until(_delegated, timeout_sec=1200, message="統合テストの委任（epic PR に 確認:complex-scenario-writer）")

    # 検証: epic Issue の 確認:* が除去され、完了報告コメントが Resolve 済み
    issue = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=epic.number).parsed_data
    assert not any(label.name.startswith("確認:") for label in issue.labels)
    assert server._is_minimized(report.node_id), "完了報告コメントが未 Resolve"


def test_normal_children_remaining(monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, epic_body, wait_until):
    """未完了の子が残る場合の状況確認の連絡を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: closed の story + open の story を持つ epic + epic Draft PR
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=epic_body, epic_labels=["layer:epic"]
    )
    done_story = _make_story(gh_live, repo_ctx, epic.number, "期限通知メールの受信", closed=True)
    open_story = _make_story(gh_live, repo_ctx, epic.number, "通知設定の変更", closed=False)
    pr = epic_pr_factory(
        branch=f"feat/epic/togo-remaining-{epic.number}", title=EPIC_TITLE, body=PR_BODY.format(epic_number=epic.number)
    )
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic.number, body=STORY_DONE_REPORT.format(story_number=done_story.number)
    )
    gh_live.rest.issues.add_labels(owner=owner, repo=repo, issue_number=epic.number, labels=["確認:epic-conductor"])

    # 実行: open の story への状況確認（確認:story-conductor + コメント）を待つ
    def _status_check_sent():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=open_story.number).parsed_data
        labels = {label.name for label in data.labels}
        return data if "確認:story-conductor" in labels else None

    wait_until(_status_check_sent, timeout_sec=1200, message="open story への状況確認（確認:story-conductor 付与）")

    # 検証: open の story に @story-conductor 宛の状況確認コメントが投稿されている
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=open_story.number).parsed_data
    assert any("> to: @story-conductor" in (c.body or "") for c in comments), "状況確認コメントが投稿されていない"

    # 待機: 状況確認送信の直後にはまだ epic 側のラベル除去が反映されていない可能性があるため、除去完了まで待つ
    def _epic_confirm_removed():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=epic.number).parsed_data
        return data if not any(label.name.startswith("確認:") for label in data.labels) else None

    wait_until(_epic_confirm_removed, timeout_sec=600, message="epic の 確認:* 除去")

    # 検証: 統合テストの委任は発生していない（epic PR に 確認:complex-scenario-writer なし）
    pr_data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    assert not any(label.name == "確認:complex-scenario-writer" for label in pr_data.labels)


def test_normal_bug_return(monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, epic_body, wait_until):
    """失敗報告 → 方針確認 → 承認 → 該当 story への差し戻しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: closed の story を持つ epic + epic Draft PR + complex-scenario-writer の失敗報告
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=epic_body, epic_labels=["layer:epic"]
    )
    story = _make_story(gh_live, repo_ctx, epic.number, "期限通知メールの受信", closed=True)
    epic_pr_factory(
        branch=f"feat/epic/togo-bug-{epic.number}", title=EPIC_TITLE, body=PR_BODY.format(epic_number=epic.number)
    )
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic.number, body=FAIL_REPORT.format(story_number=story.number)
    ).parsed_data
    gh_live.rest.issues.add_labels(owner=owner, repo=repo, issue_number=epic.number, labels=["確認:epic-conductor"])

    # 実行: バグ差し戻し（方針確認）の待機（議論中 + assignee）を待つ
    def _plan_posted():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=epic.number).parsed_data
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    issue = wait_until(_plan_posted, timeout_sec=1200, message="バグ差し戻し（方針確認）の待機（議論中 + assignee）")

    # 検証: epic-conductor の対応方針案コメントが投稿されている
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=epic.number).parsed_data
    assert any("> from: @epic-conductor" in (c.body or "") for c in comments), "対応方針案コメントが投稿されていない"

    # 実行: ユーザー承認を再現（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=epic.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in issue.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=epic.number, assignees=[assignee.login]
        )

    # 実行: 該当 story への差し戻し（reopen + 確認:story-conductor）を待つ
    def _returned():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=story.number).parsed_data
        labels = {label.name for label in data.labels}
        return data if data.state == "open" and "確認:story-conductor" in labels else None

    wait_until(_returned, timeout_sec=1200, message="story への差し戻し（reopen + 確認:story-conductor）")

    # 検証: story に @story-conductor 宛のバグ内容コメントが投稿されている
    story_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=story.number).parsed_data
    assert any("> to: @story-conductor" in (c.body or "") for c in story_comments), "バグ内容コメントが投稿されていない"

    # 待機: 差し戻し実行の直後にはまだ epic 側のラベル除去が反映されていない可能性があるため、除去完了まで待つ
    def _epic_confirm_removed():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=epic.number).parsed_data
        return data if not any(label.name.startswith("確認:") for label in data.labels) else None

    wait_until(_epic_confirm_removed, timeout_sec=600, message="epic の 確認:* 除去")

    # 検証: 失敗報告コメントに返信追記のうえ Resolve 済み
    updated_report = gh_live.rest.issues.get_comment(owner=owner, repo=repo, comment_id=report.id).parsed_data
    assert "---" in (updated_report.body or ""), "失敗報告コメントに差し戻し結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "失敗報告コメントが未 Resolve"
