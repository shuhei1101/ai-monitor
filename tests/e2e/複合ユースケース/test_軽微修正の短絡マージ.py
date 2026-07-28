"""「軽微修正の短絡マージ」の E2E テスト。"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server

INTAKE_TITLE = "README の typo を修正"
INTAKE_BODY_TEMPLATE = """`{path}` に typo があるので直してください。

- `recieve` → `receive`（1 箇所）

コードの挙動には影響しないコメントの修正です。
この Issue に含める作業はこの typo 修正だけで、他の変更は不要です。
"""

TYPO_TEXT = """# 受信処理のメモ

recieve したイベントはキューに積んでから処理する。
"""

# 短絡の検証: chore 以外のレイヤーを経由していないことを見る
NON_CHORE_LAYERS = ("layer:epic", "layer:story", "layer:subsystem")


def _issue(gh_live, owner, repo, number):
    """Issue / PR の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def _label_names(data) -> set[str]:
    """スナップショットのラベル名集合を返す。"""
    return {label.name for label in data.labels}


def _file_text(gh_live, owner, repo, path, ref) -> str:
    """指定 ref のファイル内容を返す。"""
    content = gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref).parsed_data
    return base64.b64decode(content.content).decode("utf-8")


def _open_pr_for(gh_live, owner, repo, number):
    """指定 Issue 番号を本文で参照している open PR を返す。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
    candidates = [p for p in pulls if f"#{number}" in (p.body or "")]
    return candidates[0] if candidates else None


def _approve(gh_live, owner, repo, number, assignees) -> None:
    """ユーザー役の承認操作（議論中 除去 + assignee 外し）。"""
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name="議論中")
    except RequestFailed:
        pass
    for assignee in assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def _cleanup(gh_live, owner, repo, sandbox, path: str, branch: str | None) -> None:
    """テストが master へ置いた修正対象と、残った PR / ブランチ / worktree を片付ける。"""
    # 修正対象のファイルは master にマージされるため、テスト側で削除まで戻す
    try:
        current = gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref="master").parsed_data
        gh_live.rest.repos.delete_file(
            owner=owner, repo=repo, path=path, message=f"chore: e2e 用の {path} を削除",
            sha=current.sha, branch="master",
        )
    except RequestFailed:
        pass
    if not branch:
        return
    # 途中で失敗した場合に備えて PR / ブランチ / worktree を落とす（成功時は既に無い）
    for pr in gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data:
        if pr.head.ref == branch:
            try:
                gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=pr.number, state="closed")
            except RequestFailed:
                pass
    try:
        gh_live.rest.git.delete_ref(owner=owner, repo=repo, ref=f"heads/{branch}")
    except RequestFailed:
        pass
    local_path = sandbox["local_path"]
    worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
    subprocess.run(
        ["git", "-C", local_path, "worktree", "remove", "--force", str(worktree_path)],
        capture_output=True, text=True, check=False,
    )
    subprocess.run(["git", "-C", local_path, "branch", "-D", branch], capture_output=True, text=True, check=False)


def test_normal(monitor, gh_live, repo_ctx, issue_factory, commit_file, wait_until, sandbox):
    """intake の chore 判定 → 直接マージ → intake 自動クローズの短絡経路を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: 修正対象を master に置き、対象パスを本文へ書いてから確認ラベルで起動をかける
    intake = issue_factory(INTAKE_TITLE, "", [])
    path = f"chore/typo-{intake.number}.txt"
    commit_file("master", path, TYPO_TEXT, f"chore: e2e 用に {path} を配置")
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=intake.number,
        body=INTAKE_BODY_TEMPLATE.format(path=path),
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=intake.number, labels=["確認:intake-issue-triager"]
    )

    branch: str | None = None
    try:
        # 実行: 分解判定（初回）の完了（サブ Issue 案の提示 + 待機）を待つ
        def _triage_done():
            data = _issue(gh_live, owner, repo, intake.number)
            names = _label_names(data)
            return data if "議論中" in names and data.assignees else None

        data = wait_until(_triage_done, timeout_sec=1800, message="分解判定（初回）の完了（議論中 + assignee）")

        # 検証: intake Issue に集約ラベルとサブ Issue 案コメントが揃っている
        names = _label_names(data)
        assert "layer:intake" in names, f"layer:intake がない: {sorted(names)}"
        assert any(name.startswith("type:") for name in names), f"type:* がない: {sorted(names)}"
        assert gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=intake.number
        ).parsed_data, "サブ Issue 案コメントが投稿されていない"

        # 準備: ユーザー承認（議論中 除去 + assignee 外し）
        _approve(gh_live, owner, repo, intake.number, data.assignees)

        # 実行: サブIssue起票（完了処理）の完了を待つ
        def _subissues_created():
            data = _issue(gh_live, owner, repo, intake.number)
            if any(name.startswith("確認:") for name in _label_names(data)):
                return None
            subs = gh_live.rest.issues.list_sub_issues(
                owner=owner, repo=repo, issue_number=intake.number
            ).parsed_data
            return subs or None

        subs = wait_until(_subissues_created, timeout_sec=1800, message="サブIssue起票（完了処理）の完了")

        # 検証: chore に短絡している（epic / story / subsystem のレイヤーを経由していない）
        assert len(subs) == 1, f"chore 1 件に分解されていない: {[s.title for s in subs]}"
        chore = subs[0]
        chore_labels = _label_names(chore)
        assert "layer:chore" in chore_labels, f"#{chore.number} に layer:chore がない: {sorted(chore_labels)}"
        assert "確認:quick-implementer" in chore_labels, (
            f"#{chore.number} に 確認:quick-implementer がない: {sorted(chore_labels)}"
        )
        assert not [name for name in chore_labels if name in NON_CHORE_LAYERS], (
            f"#{chore.number} に chore 以外の layer が付いている: {sorted(chore_labels)}"
        )

        # 実行: quick-implementer の 修正とPR作成（確認依頼の待機）を待つ
        def _pr_requested():
            data = _issue(gh_live, owner, repo, chore.number)
            names = _label_names(data)
            if "議論中" not in names or not data.assignees:
                return None
            pr = _open_pr_for(gh_live, owner, repo, chore.number)
            return (data, pr) if pr else None

        chore_data, pr = wait_until(
            _pr_requested, timeout_sec=1800, message="修正とPR作成の確認依頼（議論中 + assignee）"
        )
        branch = pr.head.ref

        # 検証: レビュー工程を挟まず master 直行の PR になっている
        assert pr.base.ref == "master", f"PR の base が master でない: {pr.base.ref}"
        pr_labels = {label.name for label in pr.labels}
        assert not [name for name in pr_labels if name.startswith("確認:")], (
            f"PR に確認ラベルが付いている: {sorted(pr_labels)}"
        )
        assert not gh_live.rest.pulls.list_review_comments(
            owner=owner, repo=repo, pull_number=pr.number
        ).parsed_data, "PR にレビューコメントが付いている（レビュー工程は経由しない）"

        # 準備: ユーザー承認（議論中 除去 + assignee 外し）
        _approve(gh_live, owner, repo, chore.number, chore_data.assignees)

        # 実行: マージ実行 → 全 Sub-issue closed → モニターの intake 自動クローズを待つ
        def _intake_closed():
            current = _issue(gh_live, owner, repo, intake.number)
            return current if current.state == "closed" else None

        closed_intake = wait_until(
            _intake_closed, timeout_sec=1800, message="マージと intake Issue の自動クローズ"
        )

        # 検証: intake Issue も chore Issue も close 済み
        assert closed_intake.state_reason == "completed", (
            f"intake Issue の close 理由が completed でない: {closed_intake.state_reason}"
        )
        closed_chore = _issue(gh_live, owner, repo, chore.number)
        assert closed_chore.state == "closed", "chore Issue が close されていない"

        # 検証: master に対象修正の commit が入っている
        text = _file_text(gh_live, owner, repo, path, "master")
        assert "receive" in text and "recieve" not in text, f"master に修正が反映されていない: {text!r}"
        merged = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr.number).parsed_data
        assert merged.merged is True, "PR が merged になっていない"

        # 検証: chore ブランチが sandbox から削除済み
        try:
            gh_live.rest.repos.get_branch(owner=owner, repo=repo, branch=branch)
            raise AssertionError(f"chore ブランチが残っている: {branch}")
        except RequestFailed as exc:
            assert exc.response.status_code == 404, f"想定外の応答: {exc}"

        # 検証: worktree ディレクトリがモニターローカルから削除済み
        worktree_path = Path(sandbox["local_path"]) / ".claude" / "worktrees" / branch.replace("/", "-")
        assert not worktree_path.exists(), f"worktree が残っている: {worktree_path}"

        # 検証: chore Issue の自分宛コメントが Resolve 済み
        for comment in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=chore.number
        ).parsed_data:
            if (comment.body or "").lstrip().startswith("> from: @quick-implementer"):
                assert server._is_minimized(comment.node_id), f"自分宛コメントが未 Resolve: {comment.html_url}"
    finally:
        _cleanup(gh_live, owner, repo, sandbox, path, branch)
