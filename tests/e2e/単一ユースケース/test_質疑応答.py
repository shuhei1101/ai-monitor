"""「質疑応答」の E2E テスト。"""
from __future__ import annotations

import re
import subprocess

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server

QUESTION_TITLE = "確認ラベルと議論中ラベルの使い分け"
QUESTION_BODY = """`確認:*` ラベルと `議論中` ラベルはどう使い分けるのか教えてください。

- どちらが付いているときにエージェントが起動するのか
- ユーザーはどちらを外せばよいのか
"""

CREATE_ISSUE_REQUEST = """この内容で新規 Issue を立てておいてください。

ラベルの使い分けを Wiki の 1 ページにまとめてほしいです。
"""


def _issue(gh_live, owner, repo, number):
    """Issue の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


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


def _answers(gh_live, owner, repo, number) -> list:
    """questioner 起点のコメントを投稿順で返す。"""
    return [
        c for c in gh_live.rest.issues.list_comments(
            owner=owner, repo=repo, issue_number=number
        ).parsed_data
        if (c.body or "").lstrip().startswith("> from: @questioner")
    ]


def _wait_answered(gh_live, owner, repo, number, wait_until, *, message):
    """回答の投稿と待機（議論中 + assignee）を待つ。"""

    def _done():
        data = _issue(gh_live, owner, repo, number)
        labels = {label.name for label in data.labels}
        if "議論中" not in labels or not data.assignees:
            return None
        answers = _answers(gh_live, owner, repo, number)
        return (data, answers) if answers else None

    return wait_until(_done, timeout_sec=1800, message=message)


def test_normal(monitor, gh_live, repo_ctx, issue_factory, wait_until, sandbox):
    """質問への回答と、回答確定後の Issue クローズを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    question = issue_factory(QUESTION_TITLE, QUESTION_BODY, ["type:question", "確認:questioner"])

    # 実行: 回答の投稿と待機を待つ
    data, answers = _wait_answered(
        gh_live, owner, repo, question.number, wait_until, message="回答の投稿（議論中 + assignee）"
    )

    # 検証: 回答コメントが投稿されている
    assert answers, "回答コメントが投稿されていない"

    # 準備: ユーザー承認（議論中 除去 + assignee 外し）
    _approve(gh_live, owner, repo, question.number, data.assignees)

    # 実行: 完了処理を待つ（Issue のクローズ）
    def _closed():
        current = _issue(gh_live, owner, repo, question.number)
        return current if current.state == "closed" else None

    closed = wait_until(_closed, timeout_sec=1800, message="完了処理（question Issue のクローズ）")

    # 検証: 確認ラベルが除去され、自分宛コメントが Resolve 済み
    labels = {label.name for label in closed.labels}
    assert "確認:questioner" not in labels, f"確認:questioner が残っている: {sorted(labels)}"
    for answer in _answers(gh_live, owner, repo, question.number):
        assert server._is_minimized(answer.node_id), f"自分宛コメントが未 Resolve: {answer.html_url}"

    # 検証: 実装コード・Wiki への変更が発生していない（ブランチが増えていない）
    branches = gh_live.rest.repos.list_branches(owner=owner, repo=repo, per_page=100).parsed_data
    assert [b.name for b in branches] == ["master"], (
        f"master 以外のブランチが作られている: {[b.name for b in branches]}"
    )


def test_normal_when_起票依頼(monitor, gh_live, repo_ctx, issue_factory, wait_until, sandbox):
    """応答ループ中の依頼による新規 Issue の起票を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    question = issue_factory(QUESTION_TITLE, QUESTION_BODY, ["type:question", "確認:questioner"])

    # 準備: 回答の投稿と待機まで進める
    data, answers = _wait_answered(
        gh_live, owner, repo, question.number, wait_until, message="回答の投稿（議論中 + assignee）"
    )
    known = {c.node_id for c in answers}

    # 実行: 起票の依頼（議論中 は残したまま assignee だけ外す = 応答ループの継続）
    gh_live.rest.issues.update_comment(
        owner=owner, repo=repo, comment_id=answers[-1].id,
        body=f"{answers[-1].body}\n\n---\n{CREATE_ISSUE_REQUEST}",
    )
    for assignee in data.assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=question.number, assignees=[assignee.login]
        )

    # 実行: 起票結果の返信を待つ（起票とスレッドへの返信は別呼び出しなので返信まで待つ）
    def _replied():
        thread = next(
            (c for c in gh_live.rest.issues.list_comments(
                owner=owner, repo=repo, issue_number=question.number
            ).parsed_data if c.node_id in known),
            None,
        )
        if thread is None:
            return None
        blocks = (thread.body or "").split(CREATE_ISSUE_REQUEST.strip(), 1)
        if len(blocks) < 2 or "> from: @questioner" not in blocks[1]:
            return None
        found = re.search(r"#(\d+)", blocks[1])
        return (thread, int(found.group(1))) if found else None

    thread, created_number = wait_until(
        _replied, timeout_sec=1800, message="会話からの新規 Issue 起票と起票結果の返信"
    )

    try:
        # 検証: 返信で示された Issue が intake として起票されている
        created = _issue(gh_live, owner, repo, created_number)
        labels = {label.name for label in created.labels}
        assert "確認:intake-issue-triager" in labels, f"確認:intake-issue-triager がない: {sorted(labels)}"
        assert (created.body or "").strip(), "本文が空（会話内容の要約が入っていない）"
        assert thread is not None
    finally:
        # 起票された Issue は factory の管理外なので、Issue とエージェントセッションを明示的に片付ける
        # （セッションが残るとモニター停止後も動き続け、MCP 呼び出しが全て失敗する）
        try:
            gh_live.rest.issues.update(
                owner=owner, repo=repo, issue_number=created_number,
                state="closed", state_reason="not_planned",
            )
        except RequestFailed:
            pass
        listed = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True, check=False)
        for name in listed.stdout.splitlines():
            if name.startswith(f"ai-monitor-{sandbox['name']}-{created_number}-"):
                subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True, text=True, check=False)
