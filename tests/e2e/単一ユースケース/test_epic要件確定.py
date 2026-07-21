"""「epic要件確定」の E2E テスト。"""
from __future__ import annotations

from pathlib import Path

import yaml
from githubkit.exception import RequestFailed

import server

INTAKE_TITLE = "タスク期限のメール通知機能"
INTAKE_BODY = """タスクの期限が近づいたらメールで通知する機能を追加したいです。

- 通知の on/off はユーザー設定で切り替えたい
- 通知タイミング（1 日前 / 1 時間前）も選べるようにしたい
"""
EPIC_TITLE = "タスク期限のメール通知機能"
EPIC_SECTIONS = ["## 前提条件", "## 概要", "## 背景", "## ユースケース一覧", "## 横断要件"]


def _drive_requirements(gh_live, repo_ctx, wait_until, epic_number: int, answer_body: str):
    """初回待機 → ユーザー回答 → 応答ループ → 承認 → 完了処理までをユーザー役として進める。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # モニターの polling 検知 → 要件確定（初回）の完了を待つ
    def _first_turn_done():
        data = _get(epic_number)
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    data = wait_until(_first_turn_done, timeout_sec=1200, message="要件確定（初回）の完了（議論中 + assignee）")

    # 検証: 本文に 5 セクションが揃い、対応 story 列が未起票のまま + 完了報告・確認質問コメントがある
    body = (data.body or "").replace("\r\n", "\n")
    for section in EPIC_SECTIONS:
        assert section in body, f"本文に {section} がない"
    assert "未起票" in body
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=epic_number).parsed_data
    assert comments, "完了報告・確認質問コメントが投稿されていない"

    # 実行: ユーザー回答を再現（回答コメント + assignee 外し）
    gh_live.rest.issues.create_comment(owner=owner, repo=repo, issue_number=epic_number, body=answer_body)
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=epic_number, assignees=[assignee.login]
        )

    # 応答ループの完了を待つ（assignee 再設定）
    def _reply_turn_done():
        data = _get(epic_number)
        return data if data.assignees else None

    data = wait_until(_reply_turn_done, timeout_sec=1200, message="応答ループの完了（assignee 再設定）")

    # 実行: ユーザー承認を再現（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=epic_number, name="議論中")
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=epic_number, assignees=[assignee.login]
        )

    # 要件確定（完了処理）の完了を待つ（確認:* の除去）
    def _completed():
        data = _get(epic_number)
        labels = {label.name for label in data.labels}
        return data if not any(name.startswith("確認:") for name in labels) else None

    return wait_until(_completed, timeout_sec=1200, message="要件確定（完了処理）の完了（確認:* 除去）")


def _list_epic_prs(gh_live, repo_ctx, epic_number: int) -> list:
    """epic に紐づく open PR（本文に #番号 を含む）を返す。"""
    owner, repo = repo_ctx
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open").parsed_data
    return [pr for pr in pulls if f"#{epic_number}" in (pr.body or "")]


def _assert_linked_issue_only_body(pr) -> None:
    """PR 本文のセクションが 紐づく Issue のみであることを確認する。"""
    pr_body = (pr.body or "").replace("\r\n", "\n")
    sections = [line for line in pr_body.splitlines() if line.startswith("## ")]
    assert sections == ["## 紐づく Issue"], f"PR 本文のセクションが 紐づく Issue のみでない: {sections}"


def _watch_numbers(state_path: Path, epic_number: int) -> list[int]:
    """モニター台帳から epic-conductor セッションの監視面番号一覧を返す。"""
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        # epic-conductor × epic 主番号のセッションを探す
        if entry["agent_name"] == "epic-conductor" and entry["primary_number"] == epic_number:
            return entry["watch_numbers"]
    return []


def _assert_agent_comments_resolved(gh_live, repo_ctx, issue_number: int) -> None:
    """エージェント投稿の自分宛コメントが全て Resolve 済みであることを確認する。"""
    owner, repo = repo_ctx
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=issue_number).parsed_data
    agent_comments = [c for c in comments if c.body.lstrip().startswith("> from:")]
    assert agent_comments, "エージェントのコメントが見つからない"
    for comment in agent_comments:
        assert server._is_minimized(comment.node_id), f"コメント {comment.html_url} が未 Resolve"


def test_normal_no_poc_no_ui(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, tmp_path):
    """epic 本文確定 → 承認 → epic Draft PR 作成 + complex-scenario-writer 引き継ぎを実環境で確認する（正常系）。"""
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 不要・画面変更なしと回答）
    _drive_requirements(
        gh_live, repo_ctx, wait_until, epic.number,
        answer_body="A（PoC 不要）/ A（画面変更なし）でお願いします。",
    )

    # 検証: epic Draft PR（base=master・本文は 紐づく Issue のみ）が 1 件作成され 確認:complex-scenario-writer 付与
    prs = _list_epic_prs(gh_live, repo_ctx, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True
    assert pr.base.ref == "master"
    _assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:complex-scenario-writer" in pr_labels

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in _watch_numbers(tmp_path / "state.yaml", epic.number)

    # 検証: エージェント投稿の自分宛コメントが全て Resolve 済み
    _assert_agent_comments_resolved(gh_live, repo_ctx, epic.number)


def test_normal_no_poc_with_ui(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, tmp_path):
    """epic 本文確定 → 承認 → epic Draft PR 作成 + mock-designer 引き継ぎと指示コメントを実環境で確認する（正常系）。"""
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 不要・画面変更ありと回答）
    _drive_requirements(
        gh_live, repo_ctx, wait_until, epic.number,
        answer_body="A（PoC 不要）/ B（画面変更あり: 通知設定画面を新規作成）でお願いします。",
    )

    # 検証: epic Draft PR（base=master・本文は 紐づく Issue のみ）が 1 件作成され 確認:mock-designer 付与
    prs = _list_epic_prs(gh_live, repo_ctx, epic.number)
    assert len(prs) == 1, f"epic Draft PR が 1 件でない: {[pr.number for pr in prs]}"
    pr = prs[0]
    assert pr.draft is True
    assert pr.base.ref == "master"
    _assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:mock-designer" in pr_labels

    # 検証: PR に @mock-designer 宛の指示コメントが未 Resolve で投稿されている
    owner, repo = repo_ctx
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    directed = [c for c in pr_comments if "> to: @mock-designer" in c.body]
    assert directed, "@mock-designer 宛の指示コメントが投稿されていない"
    assert not server._is_minimized(directed[-1].node_id), "指示コメントが Resolve されてしまっている"

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in _watch_numbers(tmp_path / "state.yaml", epic.number)


def test_normal_poc_required(monitor, gh_live, repo_ctx, epic_issue_factory, wait_until, tmp_path):
    """epic 本文確定 → 承認 → PoC Draft PR 作成 + epic-poc-runner 引き継ぎ（epic Draft PR なし）を実環境で確認する（正常系）。"""
    # 準備: 親 intake + 本文空の epic Issue（確認ラベル付き・assignee なし）
    intake, epic = epic_issue_factory(INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE)

    # 実行: 要件確定フローをユーザー役として進める（PoC 必要と回答）
    _drive_requirements(
        gh_live, repo_ctx, wait_until, epic.number,
        answer_body="B（PoC 必要: メール一斉送信のスループット検証）/ A（画面変更なし）でお願いします。",
    )

    # 検証: PoC Draft PR のみが 1 件作成され（epic Draft PR は作成されない）確認:epic-poc-runner 付与
    prs = _list_epic_prs(gh_live, repo_ctx, epic.number)
    assert len(prs) == 1, f"PoC Draft PR のみの 1 件でない: {[(pr.number, pr.title) for pr in prs]}"
    pr = prs[0]
    assert pr.title.startswith("PoC:"), f"タイトルが PoC: 始まりでない: {pr.title}"
    assert f"#{epic.number}" in pr.title
    assert pr.draft is True
    assert pr.base.ref == "master"
    _assert_linked_issue_only_body(pr)
    pr_labels = {label.name for label in pr.labels}
    assert "確認:epic-poc-runner" in pr_labels

    # 検証: 作成した PR の番号が自セッションの監視面（モニターの台帳）に登録されている
    assert pr.number in _watch_numbers(tmp_path / "state.yaml", epic.number)
