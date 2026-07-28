"""「バグ修正着手」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, issue, label_names
from tests.e2e.実装対象 import EPIC_BODY, EPIC_TITLE, INTAKE_BODY, INTAKE_TITLE, STORY_BODY_TEMPLATE, STORY_TITLE
from tests.e2e.統合テスト import (
    BUGGY_SERVICE_PY,
    E2E_TEST_PY,
    STORY_PR_BODY_WITH_TABLE,
    add_merged_subsystem,
    story_branch_files,
)

FIX_BRANCH_PREFIX = "fix/"

BUG_HANDOVER = """> from: @story-conductor
> to: @subsystem-conductor

単一ユースケース E2E で fail が出ました。実装側の問題です。

| 失敗ケース | 内容 |
| --- | --- |
| `test_error_when_タイトルが空` | タイトルを空にしても `ValidationError` にならず保存される |

修正方針: `src/tasks/service.py` の `update_task` のタイトル検証を「1 文字以上 100 文字以内」に戻す。
設計書（モジュール構成の例外表）と単体テストの整合も確認してください。

対応方針はユーザー承認済みです。修正用 PR の作成をお願いします。
"""


def _fix_prs(gh_live, owner, repo, subsystem_number: int) -> list:
    """修正用 PR（fix/*）の一覧を返す。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    return [
        pr for pr in pulls
        if pr.head.ref.startswith(FIX_BRANCH_PREFIX) and f"#{subsystem_number}" in (pr.body or "")
    ]


def _cleanup(gh_live, owner, repo, sandbox, subsystem_number: int) -> None:
    """作成された修正用 PR / ブランチ / worktree を片付ける。"""
    local_path = sandbox["local_path"]
    for pr in _fix_prs(gh_live, owner, repo, subsystem_number):
        branch = pr.head.ref
        try:
            gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=pr.number, state="closed")
            gh_live.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{branch}")
        except Exception:  # noqa: BLE001 — 後片付けなので失敗しても続行する
            pass
        worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
        subprocess.run(
            ["git", "-C", local_path, "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True, text=True, check=False,
        )
        subprocess.run(
            ["git", "-C", local_path, "branch", "-D", branch], capture_output=True, text=True, check=False
        )
    subprocess.run(["git", "-C", local_path, "worktree", "prune"], capture_output=True, text=True, check=False)
    # 修正用 PR は factory の掃除対象外なので、対応するセッションもここで落とす
    listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
    for session in listed.stdout.splitlines():
        if session.startswith(f"ai-monitor-{sandbox['name']}-{subsystem_number}-"):
            subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True, text=True, check=False)


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """バグ内容コメントの受領 → 修正用 PR の作成と architect への委任を確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 統合テスト待機中の story（バグ入り実装）と、マージ済み subsystem
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_branch = f"feat/epic/task-edit-{epic.number}"
    epic_pr_factory(branch=epic_branch, title=EPIC_TITLE, body=f"## 紐づく Issue\n\n- #{epic.number}\n")
    story = story_issue_factory(
        epic.number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=epic.number), labels=["layer:story", "type:feat"],
    )
    story_branch = f"feat/story/task-edit-{story.number}"
    draft_pr_factory(
        story_branch, STORY_TITLE,
        STORY_PR_BODY_WITH_TABLE.format(story_number=story.number), base_branch=epic_branch,
    )
    for path, content in story_branch_files(service=BUGGY_SERVICE_PY, e2e_test=E2E_TEST_PY).items():
        commit_file(story_branch, path, content, f"chore: e2e 用に {path} を配置")
    subsystem = add_merged_subsystem(gh_live, owner, repo, subsystem_issue_factory, story.number)

    # 準備: subsystem Issue を reopen + バグ内容コメント → 確認ラベル付与（起動トリガー）
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=subsystem.number, state="open"
    )
    handover = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=subsystem.number, body=BUG_HANDOVER
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=subsystem.number, labels=["確認:subsystem-conductor"]
    )

    try:
        # 実行: 修正用 PR の作成と architect への委任を待つ
        def _started():
            prs = _fix_prs(gh_live, owner, repo, subsystem.number)
            if not prs:
                return None
            pr = prs[0]
            labels = {label.name for label in pr.labels}
            if "確認:architect" not in labels:
                return None
            sub_now = issue(gh_live, owner, repo, subsystem.number)
            return (pr, sub_now) if "確認:subsystem-conductor" not in label_names(sub_now) else None

        fix_pr, sub_now = wait_until(
            _started, timeout_sec=1800, message="修正用 PR の作成と architect への委任"
        )

        # 検証: base が story ブランチで、ブランチ名が fix/{scope}/... になっている
        assert fix_pr.base.ref == story_branch, f"修正用 PR の base が story ブランチでない: {fix_pr.base.ref}"
        assert fix_pr.head.ref.startswith(FIX_BRANCH_PREFIX), (
            f"修正用ブランチが fix/ 始まりでない: {fix_pr.head.ref}"
        )
        assert fix_pr.draft is True, "修正用 PR が Draft でない"

        # 検証: 本文に 紐づく Issue と タスク一覧 が記入されている
        body = (fix_pr.body or "").replace("\r\n", "\n")
        assert "## 紐づく Issue" in body, "本文に ## 紐づく Issue がない"
        assert "## タスク一覧" in body, "本文に ## タスク一覧 がない"
        task_lines = [
            line for line in body.split("## タスク一覧", 1)[1].split("\n## ", 1)[0].splitlines()
            if line.strip().startswith("- [")
        ]
        assert task_lines, "タスク一覧の行がない"

        # 検証: バグ内容コメントのスレッドに修正用 PR のリンクが返信追記され、Resolve 済み
        thread = next(
            c for c in comments(gh_live, owner, repo, subsystem.number) if c.node_id == handover.node_id
        )
        assert f"#{fix_pr.number}" in (thread.body or ""), "バグ内容コメントに修正用 PR のリンクがない"
        assert server._is_minimized(handover.node_id), "バグ内容コメントが未 Resolve"

        # 検証: subsystem Issue は open のまま 確認:subsystem-conductor が除去されている
        assert sub_now.state == "open", "subsystem Issue が close されている"
    finally:
        _cleanup(gh_live, owner, repo, sandbox, subsystem.number)
