"""「複合シナリオ設計」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from githubkit.exception import RequestFailed

import server

INTAKE_TITLE = "タスク編集機能"
INTAKE_BODY = "既存タスクを編集できる機能を追加する。"

EPIC_TITLE = "タスク編集機能"
EPIC_BODY = """## 前提条件

なし

## 概要

既存タスクを一覧から選択して編集できる機能を提供する。

## 背景

現状はタスクの新規作成のみで編集導線がなく、内容の修正ができない。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| タスク編集 | 一覧から編集画面へ遷移して編集内容を保存する | 未起票 |

## 横断要件

- 保存時は既存 API を利用する
"""


def test_normal(monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, sandbox, wait_until, tmp_path):
    """シナリオ作成 → 承認 → 完了処理までを実環境で確認する（正常系）。"""
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
    # 準備: epic ブランチのローカル worktree（complex-scenario-writer が commit するため。本番では epic-conductor が worktree_create で用意する）
    local_path = sandbox["local_path"]
    worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
    subprocess.run(["git", "-C", local_path, "fetch", "origin", branch], check=True)
    subprocess.run(
        ["git", "-C", local_path, "worktree", "add", str(worktree_path), branch],
        check=True,
    )
    # 準備: 確認ラベルを付ける（前工程はなく、指示コメントは不要 = シナリオでもセットアップに指示コメントは書かれていない）
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr.number, labels=["確認:complex-scenario-writer"]
    )

    # 実行: モニターの polling 検知 → シナリオ作成の完了を待つ（議論中 + assignee + シナリオ md commit）
    def _scenario_done():
        data = _get(pr.number)
        labels = {label.name for label in data.labels}
        if not ("議論中" in labels and data.assignees):
            return None
        # epic ブランチに 複合ユースケース/*.md が commit されているか
        tree = gh_live.rest.git.get_tree(owner=owner, repo=repo, tree_sha=branch, recursive="1").parsed_data
        scenario_files = [
            t.path for t in tree.tree
            if t.path.startswith("docs/wiki/設計図/シナリオ/複合ユースケース/") and t.path.endswith(".md")
        ]
        if not scenario_files:
            return None
        return (data, scenario_files)

    pr_data, scenario_files = wait_until(
        _scenario_done, timeout_sec=1500, message="シナリオ作成の完了（議論中 + assignee + 複合UC .md commit）"
    )

    # 検証: 複合ユースケース .md が新規に commit されている（master には無いパス）
    master_tree = gh_live.rest.git.get_tree(owner=owner, repo=repo, tree_sha="master", recursive="1").parsed_data
    master_paths = {t.path for t in master_tree.tree}
    new_scenarios = [f for f in scenario_files if f not in master_paths]
    assert new_scenarios, f"新規追加された複合UC .md が見つからない（epic ブランチ: {scenario_files}）"

    # 検証: シナリオ索引 README も更新されている
    readme_epic = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path="docs/wiki/設計図/シナリオ/README.md", ref=branch
    ).parsed_data
    readme_master = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path="docs/wiki/設計図/シナリオ/README.md", ref="master"
    ).parsed_data
    assert readme_epic.sha != readme_master.sha, "シナリオ README が更新されていない"

    # 実行: シナリオ承認を再現（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=pr.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in pr_data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=pr.number, assignees=[assignee.login]
        )

    # 実行: 完了処理完了を待つ（PR の 確認:complex-scenario-writer 除去 + 親 epic に 確認:epic-conductor 付与 + @epic-conductor 宛完了報告コメント投稿）
    def _wrapped_up():
        pr_now = _get(pr.number)
        epic_now = _get(epic.number)
        pr_labels = {label.name for label in pr_now.labels}
        epic_labels = {label.name for label in epic_now.labels}
        if not ("確認:complex-scenario-writer" not in pr_labels and "確認:epic-conductor" in epic_labels):
            return None
        epic_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=epic.number).parsed_data
        completion = [c for c in epic_comments if "> to: @epic-conductor" in c.body]
        if not completion:
            return None
        return (pr_now, epic_now, completion)

    pr_data, epic_data, completion = wait_until(_wrapped_up, timeout_sec=1200, message="完了処理の完了（ラベル遷移 + 完了報告投稿）")

    # 検証: @epic-conductor 宛の完了報告コメントが未 Resolve
    assert not server._is_minimized(completion[-1].node_id), "完了報告が Resolve されてしまっている"

    # 検証: PR の自身投稿コメントが全て Resolve 済み
    pr_comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=pr.number).parsed_data
    for comment in pr_comments:
        assert server._is_minimized(comment.node_id), f"PR コメント {comment.html_url} が未 Resolve"
