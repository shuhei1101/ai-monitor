"""「現状設計書の起こし」の E2E テスト。

UC は ss-design-reverse-engineer（発注元は subsystem-conductor）で代表する。
他の reverse-engineer は成果物と発注元が違うだけで手順は同じ。
"""
from __future__ import annotations

import base64

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments_from, issue, label_names, supplement_review_comments
from tests.e2e.システム import RE_REQUEST, setup_re_target
from tests.e2e.実装対象 import SUBSYSTEM_TITLE

RE_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] 現状のモジュール構成を起こす
"""

# 現状の実装に実在する物理名（推測での補完を検出するための照合材料）
IMPLEMENTED_NAMES = ["get_task", "update_task", "list_tasks"]
# 実装に存在しない名前（推測で補完していたら現れる）
ABSENT_NAMES = ["delete_task", "create_task", "save_task"]


def _changed_files(gh_live, owner, repo, base: str, head: str) -> list[str]:
    """base..head で変更されたファイル名を返す。"""
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{base}...{head}"
    ).parsed_data
    return [f.filename for f in (compare.files or [])]


def _file_text(gh_live, owner, repo, path: str, ref: str) -> str:
    """指定 ref のファイル内容を返す。"""
    content = gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref).parsed_data
    return base64.b64decode(content.content).decode("utf-8")


def _setup_re_pr(
    gh_live, owner, repo, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, *, scope: str,
):
    """RE PR（依頼待ちの状態）までを用意する。"""
    ctx = setup_re_target(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        subsystem_labels=["layer:subsystem", f"scope:{scope}", "リバースエンジニアリング"],
    )
    subsystem_number = ctx["subsystem"].number
    re_branch = f"docs/reverse/{scope}/task-edit-{subsystem_number}"
    re_pr = draft_pr_factory(
        re_branch, f"{SUBSYSTEM_TITLE}（現状の設計書）",
        RE_PR_BODY.format(subsystem_number=subsystem_number),
        base_branch=ctx["story_branch"],
    )
    ctx["re_branch"] = re_branch
    ctx["re_pr"] = re_pr
    return ctx


def _wait_handed_back(gh_live, owner, repo, pr_number, wait_until, *, message):
    """発注元への引き渡し（確認:subsystem-conductor 付与 + 報告）を待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, pr_number)
        labels = label_names(data)
        if "確認:subsystem-conductor" not in labels or "確認:ss-design-reverse-engineer" in labels:
            return None
        reports = comments_from(gh_live, owner, repo, pr_number, "ss-design-reverse-engineer")
        return (data, reports[-1]) if reports else None

    return wait_until(_done, timeout_sec=2400, message=message)


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """実装コードからの現状設計書の作成と発注元への報告を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = _setup_re_pr(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file, scope="backend",
    )
    re_pr = ctx["re_pr"]

    # 準備: 発注元の依頼 → 確認:ss-design-reverse-engineer 付与（起動トリガー）
    request = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=re_pr.number,
        body=RE_REQUEST.format(sender="subsystem-conductor", receiver="ss-design-reverse-engineer"),
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=re_pr.number, labels=["確認:ss-design-reverse-engineer"]
    )

    # 実行: 現状設計書の commit と発注元への報告を待つ
    data, report = _wait_handed_back(
        gh_live, owner, repo, re_pr.number, wait_until, message="現状設計書の起こしの完了",
    )

    # 検証: 設計書が RE ブランチに commit されている
    changed = _changed_files(gh_live, owner, repo, ctx["story_branch"], ctx["re_branch"])
    design_files = [f for f in changed if f.startswith("docs/wiki/設計図/")]
    assert design_files, f"現状の設計書が commit されていない: {changed}"

    # 検証: 実装の物理名と一致し、実装に無い名前を推測で補完していない
    written = "\n".join(_file_text(gh_live, owner, repo, f, ctx["re_branch"]) for f in design_files)
    assert any(name in written for name in IMPLEMENTED_NAMES), (
        f"実装の物理名が設計書に現れていない: {IMPLEMENTED_NAMES}"
    )
    invented = [name for name in ABSENT_NAMES if name in written]
    assert not invented, f"実装に存在しない要素が書かれている（推測での補完）: {invented}"

    # 検証: あるべき姿への提案が混ざっていない
    proposals = [word for word in ("リファクタ", "改善案", "べきである") if word in written]
    assert not proposals, f"整理・リファクタ提案が含まれている: {proposals}"

    # 検証: 実装から読み取れなかった箇所が完了報告に載っている
    assert "読み取れなかった" in (report.body or ""), (
        f"読み取れなかった箇所が完了報告にない: {(report.body or '')[:200]}"
    )

    # 検証: 発注元宛の報告が未解決で、依頼コメントは Resolve 済み
    assert "> to: @subsystem-conductor" in (report.body or ""), "報告の宛先が発注元でない"
    assert not server._is_minimized(report.node_id), "完了報告が Resolve されている（受領は発注元）"
    assert server._is_minimized(request.node_id), "依頼コメントが未 Resolve"

    # 検証: ユーザーとの会話を持たない
    assert "議論中" not in label_names(data), "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"

    # 検証: commit 内容に対する補足事項がインラインコメントで残っている
    assert supplement_review_comments(gh_live, owner, repo, re_pr.number), (
        "補足事項のインラインコメントが投稿されていない"
    )


def test_error_no_target(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """担当範囲の実装が無いときの差し戻し報告を実環境で確認する（異常系・実装が見つからない）。"""
    owner, repo = repo_ctx
    # 実装が置かれていない scope を担当範囲にして、見つからない状態を決定的に誘発する
    ctx = _setup_re_pr(
        gh_live, owner, repo, epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file, scope="frontend",
    )
    re_pr = ctx["re_pr"]

    # 準備: 発注元の依頼 → 確認:ss-design-reverse-engineer 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=re_pr.number,
        body=RE_REQUEST.format(sender="subsystem-conductor", receiver="ss-design-reverse-engineer"),
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=re_pr.number, labels=["確認:ss-design-reverse-engineer"]
    )

    # 実行: 差し戻し報告を待つ
    _, report = _wait_handed_back(
        gh_live, owner, repo, re_pr.number, wait_until, message="実装が見つからない旨の差し戻し報告",
    )

    # 検証: 設計書が 1 ページも commit されていない
    changed = _changed_files(gh_live, owner, repo, ctx["story_branch"], ctx["re_branch"])
    design_files = [f for f in changed if f.startswith("docs/wiki/設計図/")]
    assert not design_files, f"実装が無いのに設計書が commit されている: {design_files}"

    # 検証: 差し戻し報告が未解決で発注元宛に投稿されている
    assert "> to: @subsystem-conductor" in (report.body or ""), "差し戻し報告の宛先が発注元でない"
    assert not server._is_minimized(report.node_id), "差し戻し報告が Resolve されている"
