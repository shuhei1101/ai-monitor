"""「全体UI設計」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from githubkit.exception import RequestFailed

import server

INTAKE_TITLE = "タスク編集画面の追加"
INTAKE_BODY = "既存タスク一覧画面から編集画面へ遷移して編集できるようにする。"

EPIC_TITLE = "タスク編集画面の追加"
EPIC_BODY = """## 前提条件

なし

## 概要

既存タスクを編集できる画面を新規追加する。

## 背景

現状はタスクの新規作成のみで編集導線がないため、ユーザーの利便性を上げる。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| タスク編集 | 一覧から編集画面へ遷移して編集内容を保存する | 未起票 |

## 横断要件

- 既存の一覧画面のレイアウトは変更しない
- 保存時は既存 API を利用する
"""

INSTRUCTION_BODY = """> from: @epic-conductor
> to: @mock-designer

epic 全体の UI 設計を発注します。

**画面方針の要点:**
- タスク編集画面を新規作成する（既存の一覧画面からの遷移導線を追加）
- レイアウト・スタイルは既存画面と揃える
- モックは 1 案でよい
"""


def test_normal(monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, sandbox, wait_until, tmp_path):
    """方針提案 → 承認 → モック作成 → 承認 → 完了処理までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: 5 セクション確定済みの epic Issue（確認ラベルなし）+ 親 intake
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic"]
    )
    # 準備: epic Draft PR（本文は `## 紐づく Issue` のみ）
    branch = f"feat/epic/task-edit-{epic.number}"
    pr = epic_pr_factory(
        branch=branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n"
    )
    # 準備: epic ブランチのローカル worktree（mock-designer が commit するため。本番では epic-conductor が worktree_create で用意する）
    local_path = sandbox["local_path"]
    worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
    subprocess.run(["git", "-C", local_path, "fetch", "origin", branch], check=True)
    subprocess.run(
        ["git", "-C", local_path, "worktree", "add", str(worktree_path), branch],
        check=True,
    )
    # 準備: epic-conductor の指示コメントを投稿してから確認ラベルを付ける
    instruction = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr.number, body=INSTRUCTION_BODY
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:mock-designer"]
    )

    # 実行: モニターの polling 検知 → 方針提案（初回）完了を待つ
    def _plan_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        body_now = (data.body or "").replace("\r\n", "\n")
        if "議論中" in labels and data.assignees and "### 画面一覧" in body_now:
            return data
        return None

    pr_data = wait_until(_plan_done, timeout_sec=1200, message="方針提案の完了（議論中 + assignee + ### 画面一覧 記入）")

    # 検証: PR 本文に `## UI 設計` と 2 セクション（画面一覧・画面遷移）が記入されている
    body = (pr_data.body or "").replace("\r\n", "\n")
    assert "## UI 設計" in body
    assert "### 画面一覧" in body
    assert "### 画面遷移" in body

    # 実行: 方針のユーザー承認を再現（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in pr_data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    # 実行: モック作成完了を待つ（議論中 + assignee 再セット + PR body に ### モック 記入）
    def _mock_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        body_now = (data.body or "").replace("\r\n", "\n")
        if "議論中" in labels and data.assignees and "### モック" in body_now:
            return data
        return None

    pr_data = wait_until(_mock_done, timeout_sec=1800, message="モック作成の完了（議論中 + assignee + ### モック 記入）")

    # 検証: PR 本文に 3 セクションすべて記入済み
    body = (pr_data.body or "").replace("\r\n", "\n")
    assert "### モック" in body

    # 検証: モック HTML が epic ブランチにコミットされている
    tree = gh_live.rest.git.get_tree(
        owner=owner, repo=repo, tree_sha=branch, recursive="1"
    ).parsed_data
    mock_files = [t.path for t in tree.tree if t.path.startswith("docs/mock/pages/") and t.path.endswith("index.html")]
    assert mock_files, "モック HTML が epic ブランチにコミットされていない"

    # 検証: PR に raw.githack.com の URL を含むコメント（モック URL 共有）が投稿されている
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    mock_url_comments = [c for c in pr_comments if "raw.githack.com" in c.body]
    assert mock_url_comments, "モック URL コメント（raw.githack.com）が投稿されていない"

    # 実行: モックのユーザー承認を再現（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in pr_data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    # 実行: 完了処理完了を待つ（PR の 確認:mock-designer 除去 + 親 epic に 確認:epic-conductor 付与）
    def _wrapped_up():
        pr_now = _get(pr.number)
        epic_now = _get(epic.number)
        pr_labels = {label.name for label in pr_now.labels}
        epic_labels = {label.name for label in epic_now.labels}
        if "確認:mock-designer" not in pr_labels and "確認:epic-conductor" in epic_labels:
            return (pr_now, epic_now)
        return None

    pr_data, epic_data = wait_until(_wrapped_up, timeout_sec=1200, message="完了処理の完了")

    # 検証: 親 epic Issue に @epic-conductor 宛の完了報告コメント（未 Resolve）が投稿されている
    epic_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=epic.number).parsed_data
    completion = [c for c in epic_comments if "> to: @epic-conductor" in c.body]
    assert completion, "@epic-conductor 宛の完了報告コメントが投稿されていない"
    assert not server._is_minimized(completion[-1].node_id), "完了報告が Resolve されてしまっている"

    # 検証: PR のエージェント投稿コメント + 指示コメントが全て Resolve 済み
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    for comment in pr_comments:
        assert server._is_minimized(comment.node_id), f"PR コメント {comment.html_url} が未 Resolve"
    assert server._is_minimized(instruction.node_id), "指示コメントが未 Resolve"
