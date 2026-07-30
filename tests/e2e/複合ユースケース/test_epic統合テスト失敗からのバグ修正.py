"""「epic統合テスト失敗からのバグ修正」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from tests.e2e.ゲート応答 import drive_gates
from tests.e2e.エスカレーション import comments_from, issue, label_names
from tests.e2e.実装対象 import STORY_BODY_TEMPLATE, STORY_TITLE, add_worktree
from tests.e2e.統合テスト import (
    BUGGY_SERVICE_PY,
    COMPLEX_E2E_TEST_PY,
    COMPLEX_TESTER_DONE_REPORT,
    EPIC_PR_BODY_WITH_TABLE,
    add_merged_subsystem,
    complex_result_rows,
    epic_branch_files,
    setup_epic,
)

FIX_BRANCH_PREFIX = "fix/"


def _fix_prs(gh_live, owner, repo, subsystem_number: int, *, state: str = "open") -> list:
    """バグ修正着手で作られた修正用 PR の一覧を返す。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state=state, per_page=100).parsed_data
    return [
        pr for pr in pulls
        if pr.head.ref.startswith(FIX_BRANCH_PREFIX) and f"#{subsystem_number}" in (pr.body or "")
    ]


def _was_reopened(gh_live, owner, repo, number: int) -> bool:
    """Issue が一度 reopen されたかをタイムラインで判定する。"""
    events = gh_live.rest.issues.list_events_for_timeline(
        owner=owner, repo=repo, issue_number=number, per_page=100
    ).parsed_data
    return any(getattr(e, "event", "") == "reopened" for e in events)


def _cleanup_fix_prs(gh_live, owner, repo, sandbox, subsystem_number: int) -> None:
    """途中で失敗した場合に残る修正用 PR / ブランチ / worktree を片付ける。"""
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
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
    master_baseline,
):
    """fail → 1 段ずつの差し戻しと中継 → 修正 → 再テスト → epic マージを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 実装にバグ（タイトルの空文字を素通し）を仕込む。異常シナリオの E2E だけが落ちる
    ctx = setup_epic(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory, commit_file,
        pr_body=EPIC_PR_BODY_WITH_TABLE,
        files=epic_branch_files(service=BUGGY_SERVICE_PY, complex_e2e_test=COMPLEX_E2E_TEST_PY),
    )
    # 全 story がマージ済み（closed）の状態を再現する
    story = story_issue_factory(
        ctx["epic"].number, STORY_TITLE,
        body=STORY_BODY_TEMPLATE.format(epic_number=ctx["epic"].number),
        labels=["layer:story", "type:feat"],
    )
    subsystem = add_merged_subsystem(gh_live, owner, repo, subsystem_issue_factory, story.number)
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=story.number, state="closed", state_reason="completed"
    )
    add_worktree(sandbox["local_path"], ctx["epic_branch"])
    epic_number = ctx["epic"].number
    epic_pr_number = ctx["pr"].number

    # 準備: tester のテスト実装完了報告 → 確認ラベル付与（レビューでの fail を誘発する起点）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic_pr_number, body=COMPLEX_TESTER_DONE_REPORT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=epic_pr_number, labels=["確認:complex-scenario-writer"]
    )

    try:
        # 実行: 各レイヤーの承認ゲートに応答しながら epic PR のマージまで進める
        def _faces():
            faces = [
                ("epic_issue", epic_number),
                ("story_issue", story.number),
                ("subsystem_issue", subsystem.number),
                ("epic_pr", epic_pr_number),
            ]
            faces += [("fix_pr", pr.number) for pr in _fix_prs(gh_live, owner, repo, subsystem.number)]
            return faces

        def _epic_pr_merged():
            data = gh_live.rest.pulls.get(
                owner=owner, repo=repo, pull_number=epic_pr_number
            ).parsed_data
            return data if data.merged else None

        history, merged_epic_pr = drive_gates(
            gh_live, owner, repo,
            faces=_faces,
            choices={
                ("epic_issue", "確認:epic-conductor"): None,
                ("story_issue", "確認:story-conductor"): None,
                ("subsystem_issue", "確認:subsystem-conductor"): None,
                ("fix_pr", "確認:architect"): None,
                ("fix_pr", "確認:subsystem-conductor"): None,
                ("epic_pr", "確認:complex-scenario-writer"): None,
            },
            terminal=_epic_pr_merged,
            wait_until=wait_until,
            timeout_sec=5400,
        )

        # 検証: バグ差し戻しの方針承認は epic レベルで開き、story レベルでは開いていない（中継は自動完了）
        assert ("epic_issue", "確認:epic-conductor") in history, (
            f"epic-conductor のバグ差し戻し方針ゲートが開かなかった: {history}"
        )
        assert ("story_issue", "確認:story-conductor") not in history, (
            f"中継がユーザー確認を求めた（自動完了のはず）: {history}"
        )
        assert ("fix_pr", "確認:subsystem-conductor") in history, (
            f"subsystem マージの最終承認ゲートが開かなかった: {history}"
        )

        # 検証: story / subsystem Issue とも reopen を経て再び close 済み
        for label, number in (("story", story.number), ("subsystem", subsystem.number)):
            assert _was_reopened(gh_live, owner, repo, number), f"{label} #{number} が reopen されていない"
            assert issue(gh_live, owner, repo, number).state == "closed", (
                f"{label} #{number} が close されていない"
            )

        # 検証: 新規のバグ Issue が起票されていない
        stories = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=epic_number
        ).parsed_data
        assert [s.number for s in stories] == [story.number], (
            f"epic 配下に想定外の Issue がある: {[(s.number, s.title) for s in stories]}"
        )
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=story.number
        ).parsed_data
        assert [s.number for s in subs] == [subsystem.number], (
            f"story 配下に想定外の Issue がある: {[(s.number, s.title) for s in subs]}"
        )

        # 検証: 修正用 PR（base=epic ブランチ）が epic ブランチへ merge 済み
        fix_prs = _fix_prs(gh_live, owner, repo, subsystem.number, state="closed")
        assert fix_prs, "修正用 PR（fix/*）が見つからない"
        merged_fix = [
            pr for pr in fix_prs
            if gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr.number).parsed_data.merged
        ]
        assert merged_fix, f"修正用 PR がマージされていない: {[pr.number for pr in fix_prs]}"
        for pr in merged_fix:
            assert pr.base.ref == ctx["epic_branch"], (
                f"修正用 PR #{pr.number} の base が epic ブランチでない: {pr.base.ref}"
            )

        # 検証: 再実行後のテスト結果表が全 ✅ になっている
        epic_pr_now = issue(gh_live, owner, repo, epic_pr_number)
        rows = complex_result_rows((epic_pr_now.body or "").replace("\r\n", "\n"))
        assert rows, "テスト結果表の行がない"
        for row in rows:
            assert "✅" in row, f"再実行後の結果列が ✅ で埋まっていない: {row}"

        # 検証: fail → pass の経過が親 epic Issue の writer 報告コメントに残っている
        reports = [
            (c.body or "") for c in comments_from(
                gh_live, owner, repo, epic_number, "complex-scenario-writer"
            )
        ]
        assert any("❌" in body or "失敗" in body for body in reports), (
            "writer の失敗報告が親 epic Issue に残っていない"
        )
        assert any("pass" in body or "✅" in body for body in reports), (
            "writer の全 pass 完了報告が親 epic Issue に残っていない"
        )

        # 検証: epic PR が master へ merged 状態
        assert merged_epic_pr.base.ref == "master", (
            f"epic PR の base が master でない: {merged_epic_pr.base.ref}"
        )

        # 検証: 各レイヤーの確認ラベルが解消されるまで待つ（終端処理はマージ後に続く）
        def _labels_cleared():
            for number in (epic_number, story.number, subsystem.number):
                names = label_names(issue(gh_live, owner, repo, number))
                if [name for name in names if name.startswith("確認:")]:
                    return None
            return True

        wait_until(_labels_cleared, timeout_sec=1800, message="各レイヤーの確認ラベル解消")
    finally:
        _cleanup_fix_prs(gh_live, owner, repo, sandbox, subsystem.number)
