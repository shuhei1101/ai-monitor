"""「設計からライブラリ採用まで」の E2E テスト。"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import ai_monitor.mcp.server as server
from tests.e2e.ライブラリPoC import (
    ADOPT_DECISION,
    AGREE_INSTRUCTION,
    CANDIDATE_COMPARISON,
    CANDIDATES,
    EXTERNAL_LIB_INDEX_MD,
    EXTERNAL_LIB_INDEX_PATH,
    SUBSYSTEM_PR_BODY,
    WIKI_APPROVAL,
    result_rows,
)
from tests.e2e.エスカレーション import (
    append_user_block,
    comments,
    comments_from,
    issue,
    label_names,
    me,
    tree_paths,
    wait_for_user,
)
from tests.e2e.実装対象 import add_worktree, seed_subsystem_branch, setup_subsystem

EXTERNAL_LIB_DIR = "docs/wiki/外部ライブラリ/"
POC_BRANCH_PREFIX = "poc/"


def _unassign(gh_live, owner, repo, number) -> None:
    """ユーザー役の返信操作（assignee 外しのみ・議論中 は残す）。"""
    data = issue(gh_live, owner, repo, number)
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def _new_architect_comment(gh_live, owner, repo, number, seen: set[str]):
    """subsystem PR に新しく投稿された architect のコメントを返す。"""
    for comment in comments_from(gh_live, owner, repo, number, "architect"):
        if comment.node_id not in seen:
            return comment
    return None


def _waiting_for_user(data) -> bool:
    """エージェントがターンを終えてユーザー待ちに入っているかを返す。

    `議論中` と assignee は前フェーズから残るため、ターン終了の判定には
    モニターが付ける処理中ラベルが消えていることを使う。
    """
    names = label_names(data)
    return bool(data.assignees) and not [name for name in names if name.startswith("処理中:")]


def _poc_prs(gh_live, owner, repo, subsystem_number: int, *, state: str = "open") -> list:
    """発注された PoC PR の一覧を返す。"""
    pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state=state, per_page=100).parsed_data
    return [
        p for p in pulls
        if p.head.ref.startswith(POC_BRANCH_PREFIX) and f"#{subsystem_number}" in (p.body or "")
    ]


def _sessions() -> list[str]:
    """起動中の tmux セッション名一覧を返す。"""
    listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
    return listed.stdout.splitlines()


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """PoC 発注 → 検証 → 採用決定 → Wiki 反映 → PoC 後片付けの一気通しを確認する（正常系）。"""
    owner, repo = repo_ctx
    login = me(gh_live)
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY, branch_type="docs", artifact="interface",
    )
    # 外部ライブラリ Wiki の索引を置いておく（採用結果はここへ行追加される）
    seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        design_overrides={EXTERNAL_LIB_INDEX_PATH: EXTERNAL_LIB_INDEX_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])
    pr_number = ctx["pr"].number
    subsystem_number = ctx["subsystem"].number

    # 準備: 設計の応答ループ中に発生したライブラリ選定論点（候補比較 + 検証観点）
    comparison = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number, body=CANDIDATE_COMPARISON.format(login=login)
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=["確認:architect"]
    )
    wait_for_user(gh_live, owner, repo, pr_number, login)
    seen = {comparison.node_id}

    # 実行: ユーザーが候補・検証観点に合意（assignee 外しのみ）
    append_user_block(gh_live, owner, repo, comparison, AGREE_INSTRUCTION)
    _unassign(gh_live, owner, repo, pr_number)

    # 実行: 候補ごとの PoC 発注（PoC PR 作成 + 確認:library-poc-runner + 検証指示）を待つ
    def _ordered():
        prs = _poc_prs(gh_live, owner, repo, subsystem_number)
        if len(prs) < len(CANDIDATES):
            return None
        for poc in prs:
            labels = {label.name for label in poc.labels}
            if "確認:library-poc-runner" not in labels:
                return None
            if not comments_from(gh_live, owner, repo, poc.number, "architect"):
                return None
        return prs

    poc_prs = wait_until(
        _ordered, timeout_sec=2400, message="PoC 発注（候補ごとの PoC PR + 確認:library-poc-runner + 検証指示）"
    )

    # 検証: 候補ごとに base=master の PoC PR が本文の必須セクション付きで作られている
    assert len(poc_prs) == len(CANDIDATES), (
        f"候補数と PoC PR 数が一致しない: {[p.head.ref for p in poc_prs]}"
    )
    for poc in poc_prs:
        assert poc.base.ref == "master", f"PoC PR #{poc.number} の base が master でない: {poc.base.ref}"
        body = (poc.body or "").replace("\r\n", "\n")
        for section in ("## 紐づく Issue", "## 発注元 PR", "## 検証対象", "## 調査結果", "## 検証観点と結果"):
            assert section in body, f"PoC PR #{poc.number} の本文に {section} がない"
        assert f"#{pr_number}" in body, f"PoC PR #{poc.number} の 発注元 PR に subsystem PR がない"
    poc_branches = [poc.head.ref for poc in poc_prs]
    assert {branch.rsplit("/", 1)[-1] for branch in poc_branches} == set(CANDIDATES), (
        f"PoC ブランチが候補名と対応していない: {poc_branches}"
    )

    # 検証: 候補比較コメントのスレッドに PoC PR のリンク一覧が追記されている
    thread = next(c for c in comments(gh_live, owner, repo, pr_number) if c.node_id == comparison.node_id)
    for poc in poc_prs:
        assert f"#{poc.number}" in (thread.body or ""), (
            f"候補比較スレッドに PoC PR #{poc.number} のリンクがない"
        )

    # 実行: 全候補の検証完了 → subsystem PR への結果まとめ投稿を待つ
    def _summarized():
        summary = _new_architect_comment(gh_live, owner, repo, pr_number, seen)
        if summary is None:
            return None
        data = issue(gh_live, owner, repo, pr_number)
        return (summary, data) if _waiting_for_user(data) else None

    summary, _ = wait_until(
        _summarized, timeout_sec=3600, message="全候補の検証完了と結果まとめの投稿（議論中 + assignee）"
    )
    seen.add(summary.node_id)

    # 検証: 全候補の実測値が PoC PR 本文に記録され、完了報告が Resolve 済み
    for poc in poc_prs:
        current = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=poc.number).parsed_data
        rows = result_rows(current.body or "")
        assert rows, f"PoC PR #{poc.number} の 検証観点と結果 に行がない"
        for row in rows:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            assert cells[2] and cells[2] != "-", f"PoC PR #{poc.number} の実測値が未記入: {row}"
            assert cells[3] and cells[3] != "-", f"PoC PR #{poc.number} の判定が未記入: {row}"
        for report in comments_from(gh_live, owner, repo, poc.number, "library-poc-runner"):
            assert server._is_minimized(report.node_id), (
                f"PoC PR #{poc.number} の完了報告が未 Resolve: {report.html_url}"
            )
        assert "確認:architect" not in {
            label.name for label in issue(gh_live, owner, repo, poc.number).labels
        }, f"PoC PR #{poc.number} に 確認:architect が残っている"
    for name in CANDIDATES:
        assert name in (summary.body or ""), f"結果まとめに候補 {name} の行がない"

    # 実行: ユーザーが採用ライブラリを決定（assignee 外しのみ）
    append_user_block(gh_live, owner, repo, summary, ADOPT_DECISION)
    _unassign(gh_live, owner, repo, pr_number)

    # 実行: 外部ライブラリ Wiki への反映と反映報告の投稿を待つ
    def _reflected():
        report = _new_architect_comment(gh_live, owner, repo, pr_number, seen)
        if report is None:
            return None
        paths = tree_paths(gh_live, owner, repo, ctx["subsystem_branch"], EXTERNAL_LIB_DIR)
        pages = [path for path in paths if not path.endswith("README.md")]
        if not pages:
            return None
        data = issue(gh_live, owner, repo, pr_number)
        return (report, pages) if _waiting_for_user(data) else None

    wiki_report, pages = wait_until(
        _reflected, timeout_sec=2400, message="外部ライブラリ Wiki の反映（ページ commit + 反映報告）"
    )
    seen.add(wiki_report.node_id)

    # 検証: 採用ライブラリのページと索引の行が subsystem ブランチに commit されている
    assert any("sqlite3" in path for path in pages), f"採用ライブラリのページがない: {pages}"
    index = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path=EXTERNAL_LIB_INDEX_PATH, ref=ctx["subsystem_branch"]
    ).parsed_data
    index_text = base64.b64decode(index.content).decode("utf-8")
    assert "sqlite3" in index_text, f"外部ライブラリ索引に採用行が追加されていない: {index_text!r}"

    # 実行: ユーザーが Wiki を承認（assignee 外しのみ）
    append_user_block(gh_live, owner, repo, wiki_report, WIKI_APPROVAL)
    _unassign(gh_live, owner, repo, pr_number)

    # 実行: ライブラリ選定の完了処理（PoC PR close + 後片付け + 設計応答ループへの復帰）を待つ
    def _wrapped_up():
        for poc in poc_prs:
            current = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=poc.number).parsed_data
            if current.state != "closed":
                return None
        data = issue(gh_live, owner, repo, pr_number)
        names = label_names(data)
        if "確認:architect" not in names or "議論中" not in names:
            return None
        return data if _waiting_for_user(data) else None

    final = wait_until(
        _wrapped_up, timeout_sec=2400, message="ライブラリ選定の完了処理（PoC PR close + 設計応答ループ復帰）"
    )

    # 検証: PoC PR は closed（マージなし）で残っている
    for poc in poc_prs:
        current = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=poc.number).parsed_data
        assert current.merged is False, f"PoC PR #{poc.number} がマージされている"

    # 検証: PoC ブランチがリモート / ローカル / worktree とも削除済み
    remote = {b.name for b in gh_live.rest.repos.list_branches(
        owner=owner, repo=repo, per_page=100
    ).parsed_data}
    local_path = sandbox["local_path"]
    local = subprocess.run(
        ["git", "-C", local_path, "branch", "--list"], capture_output=True, text=True, check=False
    ).stdout
    for branch in poc_branches:
        assert branch not in remote, f"PoC ブランチがリモートに残っている: {branch}"
        assert branch not in local, f"PoC ブランチがローカルに残っている: {branch}"
        worktree_path = Path(local_path) / ".claude" / "worktrees" / branch.replace("/", "-")
        assert not worktree_path.exists(), f"PoC worktree が残っている: {worktree_path}"

    # 検証: library-poc-runner の tmux セッションが全て解放済み
    def _sessions_released():
        alive = [
            name for name in _sessions()
            if any(name == f"ai-monitor-{sandbox['name']}-{poc.number}-library-poc-runner" for poc in poc_prs)
        ]
        return True if not alive else None

    wait_until(_sessions_released, timeout_sec=900, message="library-poc-runner セッションの解放")

    # 検証: ライブラリ選定関連の自分宛コメントが全て Resolve 済み
    for node_id in (comparison.node_id, summary.node_id, wiki_report.node_id):
        assert server._is_minimized(node_id), f"ライブラリ選定のコメントが未 Resolve: {node_id}"
    assert final.assignees, "設計の応答ループ（assignee=ユーザー）に戻っていない"
