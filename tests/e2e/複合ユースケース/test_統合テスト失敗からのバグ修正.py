"""「統合テスト失敗からのバグ修正」の E2E テスト。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from tests.e2e.ゲート応答 import drive_gates
from tests.e2e.エスカレーション import comments_from, issue, label_names
from tests.e2e.実装対象 import add_worktree
from tests.e2e.統合テスト import (
    BUGGY_SERVICE_PY,
    E2E_TEST_PY,
    STORY_PR_BODY_WITH_TABLE,
    TESTER_DONE_REPORT,
    add_merged_subsystem,
    result_rows,
    setup_story,
    story_branch_files,
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
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """fail → バグ差し戻し → 修正 → 再テスト → story マージの循環を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 実装にバグ（タイトルの空文字を素通し）を仕込む。異常シナリオの E2E だけが落ちる
    ctx = setup_story(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file,
        pr_body=STORY_PR_BODY_WITH_TABLE,
        files=story_branch_files(service=BUGGY_SERVICE_PY, e2e_test=E2E_TEST_PY), artifact="test",
    )
    subsystem = add_merged_subsystem(
        gh_live, owner, repo, subsystem_issue_factory, ctx["story"].number
    )
    add_worktree(sandbox["local_path"], ctx["story_branch"])
    story_number = ctx["story"].number
    story_pr_number = ctx["pr"].number

    # 準備: tester のテスト実装完了報告 → 確認ラベル付与（レビューでの fail を誘発する起点）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=story_pr_number, body=TESTER_DONE_REPORT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=story_pr_number, labels=["確認:single-scenario-writer"]
    )

    try:
        # 実行: 各レイヤーの承認ゲートに応答しながら story PR のマージまで進める
        def _faces():
            faces = [
                ("story_issue", story_number),
                ("subsystem_issue", subsystem.number),
                ("story_pr", story_pr_number),
            ]
            faces += [("fix_pr", pr.number) for pr in _fix_prs(gh_live, owner, repo, subsystem.number)]
            return faces

        def _story_pr_merged():
            data = gh_live.rest.pulls.get(
                owner=owner, repo=repo, pull_number=story_pr_number
            ).parsed_data
            return data if data.merged else None

        history, merged_story_pr = drive_gates(
            gh_live, owner, repo,
            faces=_faces,
            choices={
                ("story_issue", "確認:story-conductor"): None,
                ("subsystem_issue", "確認:subsystem-conductor"): None,
                ("fix_pr", "確認:architect"): None,
                ("fix_pr", "確認:subsystem-conductor"): None,
                ("story_pr", "確認:single-scenario-writer"): None,
            },
            terminal=_story_pr_merged,
            wait_until=wait_until,
            timeout_sec=5400,
        )

        # 検証: バグ差し戻しの方針承認ゲートと subsystem マージの最終承認ゲートを通っている
        assert ("story_issue", "確認:story-conductor") in history, (
            f"story-conductor のバグ差し戻し方針ゲートが開かなかった: {history}"
        )
        assert ("fix_pr", "確認:subsystem-conductor") in history, (
            f"subsystem マージの最終承認ゲートが開かなかった: {history}"
        )

        # 検証: 該当 subsystem Issue が reopen を経て再び close 済み
        assert _was_reopened(gh_live, owner, repo, subsystem.number), (
            f"#{subsystem.number} が reopen されていない"
        )
        current = issue(gh_live, owner, repo, subsystem.number)
        assert current.state == "closed", f"#{subsystem.number} が close されていない"

        # 検証: 新規のバグ Issue が起票されていない（差し戻し先は既存 subsystem のみ）
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=story_number
        ).parsed_data
        assert [s.number for s in subs] == [subsystem.number], (
            f"story 配下に想定外の Issue がある: {[(s.number, s.title) for s in subs]}"
        )

        # 検証: 修正用 PR が story ブランチへ merge 済み
        fix_prs = _fix_prs(gh_live, owner, repo, subsystem.number, state="closed")
        assert fix_prs, "修正用 PR（fix/*）が見つからない"
        merged_fix = [
            pr for pr in fix_prs
            if gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr.number).parsed_data.merged
        ]
        assert merged_fix, f"修正用 PR がマージされていない: {[pr.number for pr in fix_prs]}"
        for pr in merged_fix:
            assert pr.base.ref == ctx["story_branch"], (
                f"修正用 PR #{pr.number} の base が story ブランチでない: {pr.base.ref}"
            )

        # 検証: 再実行後のテスト結果表が全 ✅ になっている
        story_pr_now = issue(gh_live, owner, repo, story_pr_number)
        rows = result_rows((story_pr_now.body or "").replace("\r\n", "\n"))
        assert rows, "テスト結果表の行がない"
        for row in rows:
            assert "✅" in row, f"再実行後の結果列が ✅ で埋まっていない: {row}"

        # 検証: fail → pass の経過が親 story Issue の writer 報告コメントに残っている
        reports = [
            (c.body or "") for c in comments_from(
                gh_live, owner, repo, story_number, "single-scenario-writer"
            )
        ]
        # 失敗報告の本文は手順書が「fail 内容の要約」と定めており、`❌` はテスト結果表側にしか出ない
        assert any("fail" in body.lower() or "❌" in body or "失敗" in body for body in reports), (
            "writer の失敗報告が親 story Issue に残っていない"
        )
        assert any("pass" in body or "✅" in body for body in reports), (
            "writer の全 pass 完了報告が親 story Issue に残っていない"
        )

        # 検証: story PR が epic ブランチへ merged 状態
        assert merged_story_pr.base.ref == ctx["epic_branch"], (
            f"story PR の base が epic ブランチでない: {merged_story_pr.base.ref}"
        )

        # 検証: 各レイヤーの確認ラベルが解消されるまで待つ（完了報告はマージ後に続く）
        def _labels_cleared():
            for target in (story_number, subsystem.number):
                names = label_names(issue(gh_live, owner, repo, target))
                if [name for name in names if name.startswith("確認:")]:
                    return None
            return True

        wait_until(_labels_cleared, timeout_sec=1800, message="各レイヤーの確認ラベル解消")
    finally:
        _cleanup_fix_prs(gh_live, owner, repo, sandbox, subsystem.number)
