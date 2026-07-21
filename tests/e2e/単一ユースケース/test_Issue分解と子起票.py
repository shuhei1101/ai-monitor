"""「Issue分解と子起票」の E2E テスト。"""
from __future__ import annotations

from githubkit.exception import RequestFailed

import server

INTAKE_TITLE = "通知機能の追加 + README の typo 修正"
INTAKE_BODY = """タスクの期限が近づいたらメールで通知する機能を追加したいです。

- 通知の on/off はユーザー設定で切り替えたい
- 通知タイミング（1 日前 / 1 時間前）も選べるようにしたい

あと README のセットアップ手順に typo があるので、ついでに直しておいてください。
"""


def test_normal(monitor, gh_live, repo_ctx, intake_issue_factory, wait_until):
    """Issue 起票 → モニター検知 → 分解 → 承認 → Sub-issue 起票の一連を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    def _get(number):
        return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data

    # 準備: ユーザー起票の intake Issue（確認ラベル付き・assignee なし）
    issue = intake_issue_factory(title=INTAKE_TITLE, body=INTAKE_BODY)

    # モニターの polling 検知 → セッション作成 → 分解判定（初回）の完了を待つ
    def _first_turn_done():
        data = _get(issue.number)
        labels = {label.name for label in data.labels}
        return data if "議論中" in labels and data.assignees else None

    data = wait_until(_first_turn_done, timeout_sec=1200, message="分解判定（初回）の完了（議論中 + assignee）")

    # 検証: 案コメントの投稿と待機状態（layer / type ラベル・本文は不変）
    labels = {label.name for label in data.labels}
    assert "layer:intake" in labels
    assert any(name.startswith("type:") for name in labels)
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=issue.number).parsed_data
    assert comments, "サブ Issue 案コメントが投稿されていない"
    assert data.body.replace("\r\n", "\n") == INTAKE_BODY

    # 実行: ユーザー承認を再現（議論中 除去 + assignee 外し）
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=issue.number, name="議論中")
    except RequestFailed:
        pass
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=issue.number, assignees=[assignee.login]
        )

    # モニターの再開送信 → サブIssue起票（完了処理）の完了を待つ（確認:* の除去）
    def _completed():
        data = _get(issue.number)
        labels = {label.name for label in data.labels}
        return data if not any(name.startswith("確認:") for name in labels) else None

    data = wait_until(_completed, timeout_sec=1200, message="サブIssue起票（完了処理）の完了（確認:* 除去）")

    # 検証: 承認された案と同数の Sub-issue が親に紐づき layer:* + 確認:* が付与されている
    subs = gh_live.rest.issues.list_sub_issues(owner=owner, repo=repo, issue_number=issue.number).parsed_data
    assert subs, "Sub-issue が起票されていない"
    for sub in subs:
        sub_labels = {label.name for label in sub.labels}
        assert any(name.startswith("layer:") for name in sub_labels), f"#{sub.number} に layer:* がない"
        assert any(name.startswith("確認:") for name in sub_labels), f"#{sub.number} に 確認:* がない"

    # 検証: intake Issue は本文不変のまま layer:intake + type:* が残り open のまま
    labels = {label.name for label in data.labels}
    assert "layer:intake" in labels
    assert any(name.startswith("type:") for name in labels)
    assert data.body.replace("\r\n", "\n") == INTAKE_BODY
    assert data.state == "open"

    # 検証: エージェント投稿の自分宛コメントが全て Resolve 済み
    comments = gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=issue.number).parsed_data
    agent_comments = [c for c in comments if c.body.lstrip().startswith("> from:")]
    assert agent_comments, "エージェントのコメントが見つからない"
    for comment in agent_comments:
        assert server._is_minimized(comment.node_id), f"コメント {comment.html_url} が未 Resolve"
