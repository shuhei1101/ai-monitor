"""「story要件確定」の E2E テスト。"""
from __future__ import annotations

from pathlib import Path

import yaml
from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, issue, label_names, waiting_for_user

INTAKE_TITLE = "タスク編集機能"
INTAKE_BODY = "既存タスクを編集できる機能を追加する。"

EPIC_TITLE = "タスク編集機能"
EPIC_BODY = """## 概要

既存タスクを一覧から選択して編集できる機能を提供する。

## 背景

現状はタスクの新規作成のみで編集導線がなく、内容の修正ができない。

## ユースケース一覧

| ユースケース | 変更種別 | 概要 | 対応 story | 補足 |
| --- | --- | --- | --- | --- |
| タスク編集 | 変更 | 一覧から編集画面へ遷移して編集内容を保存する | 作成済み | - |

## 横断要件

- 保存時は既存 API を利用する
- 入力値の検証エラーは画面上でインライン表示する
"""

STORY_TITLE = "タスク編集"
SECTIONS = ["## 前提条件", "## 概要", "## 背景", "## ユースケース要件"]


def _watch_numbers(state_path: Path, story_number: int) -> list[int]:
    """モニター台帳から story-conductor セッションの監視面番号一覧を返す。"""
    entries = yaml.safe_load(state_path.read_text(encoding="utf-8")) or []
    for entry in entries:
        if entry["agent_name"] == "story-conductor" and entry["primary_number"] == story_number:
            return entry["watch_numbers"]
    return []


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, story_issue_factory,
    wait_until, e2e_state_path,
):
    """本文 4 セクションの確定 → 承認 → story Draft PR 作成までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: ユースケース一覧 確定済みの epic Issue + epic Draft PR + 本文空の story Issue
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}/base"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    story = story_issue_factory(epic.number, STORY_TITLE)

    # 実行: 要件確定（初回）の完了を待つ
    def _drafted():
        data = issue(gh_live, owner, repo, story.number)
        return data if waiting_for_user(data) else None

    data = wait_until(_drafted, timeout_sec=1800, message="要件確定（初回）の完了（議論中 + assignee）")

    # 検証: 本文に 4 セクションが揃い、背景に親 epic の UC 対応が書かれている
    body = (data.body or "").replace("\r\n", "\n")
    for section in SECTIONS:
        assert section in body, f"story 本文に {section} がない"
    assert f"#{epic.number}" in body, "背景に親 epic の番号がない"
    assert "タスク編集" in body, "背景に対応する UC 名がない"
    assert comments(gh_live, owner, repo, story.number), "完了報告・確認質問コメントが投稿されていない"

    # 実行: ユーザー承認（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=story.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=story.number, assignees=[assignee.login]
        )

    # 実行: 完了処理（story Draft PR 作成 + 確認:single-scenario-writer 付与）を待つ
    def _pr_created():
        story_now = issue(gh_live, owner, repo, story.number)
        if "確認:story-conductor" in label_names(story_now):
            return None
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        candidates = [p for p in pulls if f"#{story.number}" in (p.body or "")]
        if not candidates:
            return None
        pr = candidates[0]
        labels = {label.name for label in pr.labels}
        return pr if "確認:single-scenario-writer" in labels else None

    pr = wait_until(
        _pr_created, timeout_sec=1800, message="story Draft PR の作成（確認:single-scenario-writer 付与）"
    )

    # 検証: base が親 epic ブランチで、本文は 紐づく Issue のみ
    assert pr.draft is True, "story PR が Draft でない"
    assert pr.base.ref == epic_branch, f"base が親 epic ブランチでない: {pr.base.ref}"
    pr_body = (pr.body or "").replace("\r\n", "\n")
    sections = [line for line in pr_body.splitlines() if line.startswith("## ")]
    assert sections == ["## 紐づく Issue", "## タスク一覧"], (
        f"PR 本文のセクションが 紐づく Issue + タスク一覧 でない: {sections}"
    )
    tasks = [line.strip() for line in pr_body.splitlines() if line.strip().startswith("- [")]
    assert tasks, "タスク一覧に行がない"
    assert all(line.startswith("- [ ]") for line in tasks), (
        f"作成時点でチェック済みの行がある（チェックは各作業者が入れる）: {tasks}"
    )

    # 検証: 作成した PR の番号が自セッションの監視面に登録されている
    assert pr.number in _watch_numbers(e2e_state_path, story.number), (
        "作成した PR の番号が監視面に登録されていない"
    )

    # 検証: story Issue の自分宛コメントが全て Resolve 済み
    for comment in comments(gh_live, owner, repo, story.number):
        if (comment.body or "").lstrip().startswith("> from: @story-conductor"):
            assert server._is_minimized(comment.node_id), f"自分宛コメントが未 Resolve: {comment.html_url}"


# base（親 epic ブランチ）にある現状の単一 UC シナリオ（RE PR がマージ済みの状態）
CURRENT_SCENARIO_PATH = "docs/wiki/設計図/シナリオ/単一ユースケース/タスク編集.md"
CURRENT_SCENARIO_MD = """# タスク編集

現状の実装から起こした単一 UC。

## 正常シナリオ

### 期待値

- 一覧に編集後のタイトルと本文が表示されている

## 異常シナリオ（タイトルが空）

### 期待値

- インラインエラーが表示され、保存されていない
"""


def test_normal_when_reverse(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, story_issue_factory,
    commit_file, wait_until, e2e_state_path,
):
    """現状のシナリオを入力にした story 要件確定を実環境で確認する（正常系・リバースエンジニアリング）。"""
    owner, repo = repo_ctx
    # 準備: RE 経路の epic / story Issue と、現状のシナリオが入った epic ブランチ
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY,
        epic_labels=["layer:epic", "type:docs", "リバースエンジニアリング"],
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}/base"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    commit_file(epic_branch, CURRENT_SCENARIO_PATH, CURRENT_SCENARIO_MD, "docs: 現状の単一UC シナリオを追加")
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        labels=["layer:story", "type:docs", "リバースエンジニアリング", "確認:story-conductor"],
    )

    # 実行: 要件確定（初回）の完了を待つ
    def _drafted():
        data = issue(gh_live, owner, repo, story.number)
        return data if waiting_for_user(data) else None

    data = wait_until(_drafted, timeout_sec=1800, message="要件確定（初回）の完了（議論中 + assignee）")

    # 検証: 本文 4 セクションが揃い、現状のシナリオの振る舞いが要件に落ちている
    body = (data.body or "").replace("\r\n", "\n")
    for section in SECTIONS:
        assert section in body, f"story 本文に {section} がない"
    assert f"#{epic.number}" in body, "背景に親 epic の番号がない"
    assert comments(gh_live, owner, repo, story.number), "完了報告・確認質問コメントが投稿されていない"

    # 実行: ユーザー承認（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=story.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=story.number, assignees=[assignee.login]
        )

    # 実行: 完了処理（story Draft PR 作成 + 確認:single-scenario-writer 付与）を待つ
    def _pr_created():
        if "確認:story-conductor" in label_names(issue(gh_live, owner, repo, story.number)):
            return None
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        candidates = [p for p in pulls if f"#{story.number}" in (p.body or "")]
        if not candidates:
            return None
        pr = candidates[0]
        return pr if "確認:single-scenario-writer" in {label.name for label in pr.labels} else None

    pr = wait_until(_pr_created, timeout_sec=1800, message="story Draft PR の作成（RE 経路）")

    # 検証: base が親 epic ブランチで、本文は 紐づく Issue のみ
    assert pr.draft is True, "story PR が Draft でない"
    assert pr.base.ref == epic_branch, f"base が親 epic ブランチでない: {pr.base.ref}"

    # 検証: 作成した PR の番号が自セッションの監視面に登録されている
    assert pr.number in _watch_numbers(e2e_state_path, story.number), (
        "作成した PR の番号が監視面に登録されていない"
    )
    assert intake is not None
