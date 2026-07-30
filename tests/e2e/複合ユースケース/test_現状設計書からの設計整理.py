"""「現状設計書からの設計整理」の E2E テスト。

UC は subsystem レベルで代表する（全レイヤーが同型）。
RE PR で現状を起こし、マージ後に通常 PR であるべき構造へ整理するまでを 1 本で通す。
"""
from __future__ import annotations

import base64

from githubkit.exception import RequestFailed

from tests.e2e.ゲート応答 import drive_gates
from tests.e2e.エスカレーション import comments, issue, label_names
from tests.e2e.システム import setup_re_target

RE_LABELS = ["layer:subsystem", "scope:backend", "リバースエンジニアリング", "確認:subsystem-conductor"]
MODULE_PATH = "docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md"


def _exists(gh_live, owner, repo, path: str, ref: str) -> bool:
    """指定 ref にファイルが存在するかを返す。"""
    try:
        gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref)
        return True
    except RequestFailed:
        return False


def _file_text(gh_live, owner, repo, path: str, ref: str) -> str:
    """指定 ref のファイル内容を返す。"""
    content = gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref).parsed_data
    return base64.b64decode(content.content).decode("utf-8")


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """RE PR の起動から現状の起こし・マージ・あるべき構造への整理までを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_re_target(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        subsystem_labels=RE_LABELS,
    )
    subsystem_number = ctx["subsystem"].number

    def _faces():
        # subsystem Issue と、それに紐づく open PR（RE PR → 通常 PR）が応答対象の面
        faces = [("subsystem_issue", subsystem_number)]
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        faces += [("subsystem_pr", p.number) for p in pulls if f"#{subsystem_number}" in (p.body or "")]
        return faces

    def _assigned_to_tester():
        # 設計が確定して tester へ割り当てられた時点で終端
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        for pr in pulls:
            if f"#{subsystem_number}" not in (pr.body or ""):
                continue
            if "確認:tester" in label_names(issue(gh_live, owner, repo, pr.number)):
                return pr
        return None

    # 実行: RE 起動 → 現状の起こし → マージ → 要件確定 → SS 設計 の各ゲートに応答して終端まで進める
    history, subsystem_pr = drive_gates(
        gh_live, owner, repo,
        faces=_faces,
        choices={
            ("subsystem_issue", "確認:subsystem-conductor"): None,
            ("subsystem_pr", "確認:subsystem-conductor"): None,
            ("subsystem_pr", "確認:architect"): None,
        },
        terminal=_assigned_to_tester,
        wait_until=wait_until,
        timeout_sec=7200,
    )
    assert history, "ユーザー確認ゲートが 1 度も開いていない"

    # 検証: RE PR がマージされ、story ブランチに現状の設計書が入っている
    closed_prs = gh_live.rest.pulls.list(owner=owner, repo=repo, state="closed", per_page=100).parsed_data
    re_prs = [p for p in closed_prs if f"#{subsystem_number}" in (p.body or "") and p.merged_at]
    assert re_prs, "RE PR が merged になっていない"
    branches = {b.name for b in gh_live.rest.repos.list_branches(
        owner=owner, repo=repo, per_page=100
    ).parsed_data}
    for pr in re_prs:
        assert pr.head.ref not in branches, f"マージした RE ブランチが残っている: {pr.head.ref}"
    assert _exists(gh_live, owner, repo, MODULE_PATH, ctx["story_branch"]), (
        "story ブランチに現状の設計書が入っていない"
    )

    # 検証: 通常 PR の差分が現状からあるべき構造への変更範囲になっている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{ctx['story_branch']}...{subsystem_pr.head.ref}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    design_changes = [f for f in changed if f.startswith("docs/wiki/設計図/")]
    assert design_changes, f"設計 Wiki の変更がない: {changed}"

    # 検証: 設計 Wiki の構成要素が実装の物理名と対応づいている
    written = "\n".join(
        _file_text(gh_live, owner, repo, f, subsystem_pr.head.ref) for f in design_changes
    )
    assert any(name in written for name in ("get_task", "update_task", "list_tasks")), (
        "設計 Wiki が実装の物理名と対応づいていない"
    )

    # 検証: 現状とあるべき構造の差分がコメントで合意されている
    proposals = [
        c for c in comments(gh_live, owner, repo, subsystem_pr.number)
        if "現状" in (c.body or "") or "リファクタ" in (c.body or "")
    ]
    assert proposals, "現状とあるべき構造の差分がコメントに残っていない"

    # 検証: 処理中ラベルがどこにも残っていない
    for number in (subsystem_number, subsystem_pr.number):
        names = label_names(issue(gh_live, owner, repo, number))
        assert not [n for n in names if n.startswith("処理中:")], (
            f"#{number} に処理中ラベルが残っている: {sorted(names)}"
        )
