"""「リセット実行」の E2E テスト。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.実装対象 import SUBSYSTEM_PR_BODY, add_worktree, seed_subsystem_branch, setup_subsystem


def _issue(gh_live, owner, repo, number):
    """Issue の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def test_normal(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    subsystem_issue_factory,
    commit_file,
    wait_until,
    sandbox,
):
    """子孫 Issue / PR / ブランチ / worktree の巻き戻しを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 進行途中の状態（epic → story → subsystem と各 PR・worktree）を作る
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])

    # 準備: ユーザーが epic Issue に 確認:resetter を付与（唯一のユーザー手動起動）
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["epic"].number, labels=["確認:resetter"]
    )

    # 実行: 巻き戻し対象一覧の投稿と待機（議論中 + assignee）を待つ
    def _listed():
        data = _issue(gh_live, owner, repo, ctx["epic"].number)
        labels = {label.name for label in data.labels}
        if "議論中" not in labels or not data.assignees:
            return None
        comments = [
            c for c in gh_live.rest.issues.list_comments(
                owner=owner, repo=repo, issue_number=ctx["epic"].number
            ).parsed_data
            if (c.body or "").lstrip().startswith("> from: @resetter")
        ]
        return (data, comments) if comments else None

    data, listed = wait_until(
        _listed, timeout_sec=1800, message="巻き戻し対象一覧の投稿（議論中 + assignee）"
    )

    # 検証: 一覧に子孫 Issue と PR が並んでいる
    body = listed[-1].body or ""
    for number in (ctx["story"].number, ctx["subsystem"].number, ctx["pr"].number):
        assert f"#{number}" in body, f"巻き戻し対象一覧に #{number} が載っていない"

    # 検証: この時点ではまだ何も消えていない
    assert _issue(gh_live, owner, repo, ctx["story"].number).state == "open", (
        "承認前に子 story が閉じられている"
    )

    # 準備: ユーザー承認（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(
            owner=owner, repo=repo, issue_number=ctx["epic"].number, name="議論中"
        )
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=ctx["epic"].number, assignees=[assignee.login]
        )

    # 実行: 巻き戻しの実行（対象 Issue のクローズ）を待つ
    def _reset():
        current = _issue(gh_live, owner, repo, ctx["epic"].number)
        return current if current.state == "closed" else None

    closed = wait_until(_reset, timeout_sec=2400, message="巻き戻しの実行（epic Issue のクローズ）")

    # 検証: 子孫 Issue が全て closed
    for name, number in (("story", ctx["story"].number), ("subsystem", ctx["subsystem"].number)):
        child = _issue(gh_live, owner, repo, number)
        assert child.state == "closed", f"子 {name} Issue が closed になっていない"

    # 検証: 配下の PR が closed（マージなし）でブランチが削除されている
    branches = {b.name for b in gh_live.rest.repos.list_branches(
        owner=owner, repo=repo, per_page=100
    ).parsed_data}
    for name, number, branch in (
        ("epic", ctx["epic_pr"].number, ctx["epic_branch"]),
        ("story", ctx["story_pr"].number, ctx["story_branch"]),
        ("subsystem", ctx["pr"].number, ctx["subsystem_branch"]),
    ):
        pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=number).parsed_data
        assert pr_now.state == "closed", f"{name} PR が closed になっていない"
        assert pr_now.merged is False, f"{name} PR がマージされている（巻き戻しはマージしない）"
        assert branch not in branches, f"{name} ブランチが残っている: {branch}"

    # 検証: 確認ラベルが除去され、自分宛コメントが Resolve 済み
    labels = {label.name for label in closed.labels}
    assert not [name for name in labels if name.startswith("確認:")], (
        f"確認ラベルが残っている: {sorted(labels)}"
    )
    for comment in gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["epic"].number
    ).parsed_data:
        if (comment.body or "").lstrip().startswith("> from: @resetter"):
            assert server._is_minimized(comment.node_id), f"自分宛コメントが未 Resolve: {comment.html_url}"
