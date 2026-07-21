"""「story要件確定」の E2E テスト。"""
from __future__ import annotations

from pathlib import Path

import yaml
from githubkit.exception import RequestFailed

import server

INTAKE_TITLE = "タスク期限のメール通知機能"
INTAKE_BODY = "タスクの期限が近づいたらメールで通知する機能を追加する。"
EPIC_TITLE = "タスク期限のメール通知機能"
STORY_TITLE = "期限通知メールの受信"
STORY_SECTIONS = ["## 前提条件", "## 概要", "## 背景", "## ユースケース要件"]


def _watch_numbers(state_path: Path, story_number: int) -> list[int]:
    """モニター台帳から story-conductor セッションの監視面番号一覧を返す。"""
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        # story-conductor × story 主番号のセッションを探す
        if entry["agent_name"] == "story-conductor" and entry["primary_number"] == story_number:
            return entry["watch_numbers"]
    return []


def test_normal(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    story_issue_factory,
    epic_body,
    wait_until,
    tmp_path,
):
    """story 本文確定 → 承認 → story Draft PR 作成 + single-scenario-writer 引き継ぎを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: 5 セクション確定済みの epic Issue（確認ラベルなし・親 intake 付き）
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE,
        epic_body=epic_body, epic_labels=["layer:epic", "type:feat"],
    )
    # 準備: epic Draft PR（base=master・本文は `## 紐づく Issue` のみ）
    epic_branch = f"feat/epic/task-deadline-notification-{epic.number}"
    epic_pr_factory(
        branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n"
    )
    # 準備: 子 story Issue（layer:story + 確認:story-conductor + 本文空）
    story = story_issue_factory(epic.number, STORY_TITLE)

    # 実行: モニターの polling 検知 → 要件確定（初回）の完了を待つ（議論中 + assignee）
    def _first_turn_done():
        data = _get(story.number)
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    data = wait_until(_first_turn_done, timeout_sec=1200, message="要件確定（初回）の完了（議論中 + assignee）")

    # 検証: 本文に 4 セクション + 親 epic 番号の背景記述 + 確認質問コメントがある
    body = (data.body or "").replace("\r\n", "\n")
    for section in STORY_SECTIONS:
        assert section in body, f"本文に {section} がない"
    assert f"#{epic.number}" in body, "背景に親 epic の番号がない"
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=story.number).parsed_data
    assert comments, "完了報告・確認質問コメントが投稿されていない"

    # 実行: ユーザー回答（回答コメント + assignee 外し）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story.number,
        body="A（1 UC で表現できている）でお願いします。",
    )
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=story.number, assignees=[assignee.login]
        )

    # 応答ループの完了を待つ（assignee 再設定）
    def _reply_turn_done():
        data = _get(story.number)
        return data if data.assignees else None

    data = wait_until(_reply_turn_done, timeout_sec=1200, message="応答ループの完了（assignee 再設定）")

    # 実行: ユーザー承認（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=story.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=story.number, assignees=[assignee.login]
        )

    # 要件確定（完了処理）の完了を待つ（確認:* の除去）
    def _completed():
        data = _get(story.number)
        labels = {label.name for label in data.labels}
        return data if not any(name.startswith("確認:") for name in labels) else None

    wait_until(_completed, timeout_sec=1200, message="要件確定（完了処理）の完了（確認:* 除去）")

    # 検証: story Draft PR（base=親 epic ブランチ・本文は `## 紐づく Issue` のみ）が 1 件作成され 確認:single-scenario-writer 付与
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open").parsed_data
    story_prs = [pr for pr in pulls if f"#{story.number}" in (pr.body or "")]
    assert len(story_prs) == 1, f"story Draft PR が 1 件でない: {[pr.number for pr in story_prs]}"
    pr = story_prs[0]
    assert pr.draft is True
    assert pr.base.ref == epic_branch, f"story PR の base が親 epic ブランチでない: {pr.base.ref}"
    pr_body = (pr.body or "").replace("\r\n", "\n")
    sections = [line for line in pr_body.splitlines() if line.startswith("## ")]
    assert sections == ["## 紐づく Issue"], f"PR 本文のセクションが 紐づく Issue のみでない: {sections}"
    pr_labels = {label.name for label in pr.labels}
    assert "確認:single-scenario-writer" in pr_labels

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in _watch_numbers(tmp_path / "state.yaml", story.number)

    # 検証: エージェント投稿の自分宛コメントが全て Resolve 済み
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=story.number).parsed_data
    agent_comments = [c for c in comments if c.body.lstrip().startswith("> from:")]
    assert agent_comments, "エージェントのコメントが見つからない"
    for comment in agent_comments:
        assert server._is_minimized(comment.node_id), f"コメント {comment.html_url} が未 Resolve"
