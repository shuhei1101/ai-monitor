"""「軽微修正の直接マージ」の E2E テスト。"""
from __future__ import annotations

import base64

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server

CHORE_TITLE = "typo 修正: recieve → receive"
CHORE_BODY_TEMPLATE = """`{path}` に typo があるので直してください。

- `recieve` → `receive`（1 箇所）

コードの挙動には影響しないコメントの修正です。
"""

TYPO_TEXT = """# 受信処理のメモ

recieve したイベントはキューに積んでから処理する。
"""


def _issue(gh_live, owner, repo, number):
    """Issue の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def _file_text(gh_live, owner, repo, path, ref) -> str:
    """指定 ref のファイル内容を返す。"""
    content = gh_live.rest.repos.get_content(owner=owner, repo=repo, path=path, ref=ref).parsed_data
    return base64.b64decode(content.content).decode("utf-8")


def test_normal(monitor, gh_live, repo_ctx, issue_factory, commit_file, wait_until, sandbox):
    """指示どおりの修正・PR 作成・ユーザー確認後の直接マージを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    chore = issue_factory(CHORE_TITLE, "", ["layer:chore", "type:chore"])
    path = f"chore/typo-{chore.number}.txt"
    # 修正対象を master に置いてから、対象パスを本文に書いて起動をかける
    commit_file("master", path, TYPO_TEXT, f"chore: e2e 用に {path} を配置")
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=chore.number, body=CHORE_BODY_TEMPLATE.format(path=path)
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=chore.number, labels=["確認:quick-implementer"]
    )

    # 実行: 修正 + PR 作成 → 確認依頼の待機（議論中 + assignee）を待つ
    def _requested():
        data = _issue(gh_live, owner, repo, chore.number)
        labels = {label.name for label in data.labels}
        if "議論中" not in labels or not data.assignees:
            return None
        pulls = gh_live.rest.pulls.list(owner=owner, repo=repo, state="open", per_page=100).parsed_data
        candidates = [p for p in pulls if f"#{chore.number}" in (p.body or "")]
        return (data, candidates[0]) if candidates else None

    data, pr = wait_until(_requested, timeout_sec=1800, message="修正 + PR 作成の確認依頼（議論中 + assignee）")

    # 検証: PR がレビュー工程に出ていない（確認ラベルもレビューコメントもない）
    pr_labels = {label.name for label in pr.labels}
    assert not [name for name in pr_labels if name.startswith("確認:")], (
        f"PR に確認ラベルが付いている: {sorted(pr_labels)}"
    )
    review_comments = gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=pr.number
    ).parsed_data
    assert not review_comments, "PR にレビューコメントが付いている（レビュー工程は経由しない）"

    # 検証: PR 本文に紐づく Issue と概要が入っている
    pr_body = (pr.body or "").replace("\r\n", "\n")
    assert "## 紐づく Issue" in pr_body, "PR 本文に ## 紐づく Issue がない"
    assert "## 概要" in pr_body, "PR 本文に ## 概要 がない"

    # 準備: ユーザー承認（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(
            owner=owner, repo=repo, issue_number=chore.number, name="議論中"
        )
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=chore.number, assignees=[assignee.login]
        )

    # 実行: マージと chore Issue のクローズを待つ
    def _merged():
        current = _issue(gh_live, owner, repo, chore.number)
        if current.state != "closed":
            return None
        pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=pr.number).parsed_data
        return (current, pr_now) if pr_now.merged else None

    closed, pr_merged = wait_until(_merged, timeout_sec=1800, message="マージと chore Issue のクローズ")

    # 検証: master に修正が入っている
    text = _file_text(gh_live, owner, repo, path, "master")
    assert "receive" in text and "recieve" not in text, f"master に修正が反映されていない: {text!r}"

    # 検証: マージ後にブランチが削除されている
    assert pr_merged.merged is True, "PR が merged になっていない"
    branches = {b.name for b in gh_live.rest.repos.list_branches(
        owner=owner, repo=repo, per_page=100
    ).parsed_data}
    assert pr.head.ref not in branches, f"マージしたブランチが残っている: {pr.head.ref}"

    # 検証: 確認ラベルが除去され、自分宛コメントが Resolve 済み
    labels = {label.name for label in closed.labels}
    assert "確認:quick-implementer" not in labels, f"確認:quick-implementer が残っている: {sorted(labels)}"
    for comment in gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=chore.number
    ).parsed_data:
        if (comment.body or "").lstrip().startswith("> from: @quick-implementer"):
            assert server._is_minimized(comment.node_id), f"自分宛コメントが未 Resolve: {comment.html_url}"
