"""epic 起動系の E2E で共有するユーザー役の操作。

epic 要件確定と実現可能性 PoC は「エージェントが待機する → ユーザーが答える」の応答ループを
何度も踏むため、待機と操作をドライバに寄せてテスト側は期待値の検証だけを持つ。
"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import approve, comments, issue, label_names, waiting_for_user

# 要件確定で epic PR 本文に揃うセクション（PR 本文テンプレート『エピック』の必須セクション）
EPIC_SECTIONS = ["## 紐づく Issue", "## 概要", "## 背景", "## ユースケース一覧", "## 横断要件"]


def _no_confirm_label(data) -> bool:
    """確認ラベルが 1 つも付いていないかを返す。"""
    return not [name for name in label_names(data) if name.startswith("確認:")]


def answer(gh_live, owner, repo, number: int, body: str, assignees) -> None:
    """ユーザー役の回答操作（回答コメント投稿 + assignee 外し）。"""
    gh_live.rest.issues.create_comment(owner=owner, repo=repo, issue_number=number, body=body)
    for assignee in assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def drive_requirements(gh_live, owner, repo, wait_until, epic_number: int, *, answer_body: str):
    """epic 要件確定を 初回待機 → 回答 → 応答ループ → 承認 → 完了処理 まで進める。

    初回ターンと完了処理後の epic Issue スナップショットを返す。
    """
    # 草案作成 → 確認質問 → 待機（議論中 + assignee）の完了を待つ
    def _first_turn_done():
        data = issue(gh_live, owner, repo, epic_number)
        return data if waiting_for_user(data) else None

    first = wait_until(
        _first_turn_done, timeout_sec=1200, message="要件確定（初回）の完了（議論中 + assignee）"
    )

    # PoC 要否・画面変更有無への回答を投稿してエージェントのターンへ戻す
    answer(gh_live, owner, repo, epic_number, answer_body, first.assignees)

    # 応答ループの完了を待つ（assignee 再設定）
    def _reply_turn_done():
        data = issue(gh_live, owner, repo, epic_number)
        return data if data.assignees else None

    replied = wait_until(
        _reply_turn_done, timeout_sec=1200, message="応答ループの完了（assignee 再設定）"
    )

    # ユーザー承認（議論中 除去 + assignee 外し）で完了処理へ進ませる
    approve(gh_live, owner, repo, epic_number, replied.assignees)

    # 完了処理の完了を待つ（確認:* の除去）
    def _completed():
        data = issue(gh_live, owner, repo, epic_number)
        return data if _no_confirm_label(data) else None

    completed = wait_until(
        _completed, timeout_sec=1200, message="要件確定（完了処理）の完了（確認:* 除去）"
    )
    return first, completed


def drive_poc_verification(gh_live, owner, repo, wait_until, poc_number: int):
    """実現可能性 PoC を 方針固め → 承認 → 検証実行 → 承認 → 完了処理 まで進める。

    方針固めと検証実行それぞれの PoC PR スナップショットを返す。
    """
    # 本文の仮埋め → 確認質問 → 待機の完了を待つ
    def _plan_done():
        data = issue(gh_live, owner, repo, poc_number)
        return data if waiting_for_user(data) else None

    planned = wait_until(_plan_done, timeout_sec=1800, message="方針固めの完了（議論中 + assignee）")

    # ユーザー承認（検証構成の確定）で検証実行へ進ませる
    approve(gh_live, owner, repo, poc_number, planned.assignees)

    # 検証コードの実装と実行を経て結果が本文に記入されるのを待つ
    def _result_reported():
        data = issue(gh_live, owner, repo, poc_number)
        body = (data.body or "").replace("\r\n", "\n")
        return data if waiting_for_user(data) and "## 検証結果" in body else None

    verified = wait_until(
        _result_reported, timeout_sec=2400, message="検証実行の完了（検証結果記入 + 議論中 + assignee）"
    )

    # ユーザー承認（結果の確定）で完了処理へ進ませる
    approve(gh_live, owner, repo, poc_number, verified.assignees)

    # 完了処理の完了を待つ（PoC PR の 確認:* 除去）
    def _wrapped_up():
        data = issue(gh_live, owner, repo, poc_number)
        return data if _no_confirm_label(data) else None

    wait_until(_wrapped_up, timeout_sec=1800, message="完了処理の完了（PoC PR の 確認:* 除去）")
    return planned, verified


def assert_linked_issue_only_body(pr) -> None:
    """PR 本文のセクションが 紐づく Issue のみであることを確認する。"""
    body = (pr.body or "").replace("\r\n", "\n")
    sections = [line for line in body.splitlines() if line.startswith("## ")]
    assert sections == ["## 紐づく Issue"], f"PR 本文のセクションが 紐づく Issue のみでない: {sections}"


def assert_task_list_body(pr) -> None:
    """PR 本文が 紐づく Issue + 全行未チェックのタスク一覧であることを確認する。"""
    body = (pr.body or "").replace("\r\n", "\n")
    sections = [line for line in body.splitlines() if line.startswith("## ")]
    assert sections == ["## 紐づく Issue", "## タスク一覧"], (
        f"PR 本文のセクションが 紐づく Issue + タスク一覧 でない: {sections}"
    )
    tasks = [line.strip() for line in body.splitlines() if line.strip().startswith("- [")]
    assert tasks, "タスク一覧に行がない"
    assert all(line.startswith("- [ ]") for line in tasks), (
        f"作成時点でチェック済みの行がある（チェックは各作業者が入れる）: {tasks}"
    )


def assert_comments_resolved(gh_live, owner, repo, number: int) -> None:
    """エージェント投稿のコメントが全て Resolve 済みであることを確認する。"""
    agent_comments = [
        c for c in comments(gh_live, owner, repo, number)
        if (c.body or "").lstrip().startswith("> from:")
    ]
    assert agent_comments, f"#{number} にエージェントのコメントが見つからない"
    for comment in agent_comments:
        assert server._is_minimized(comment.node_id), f"コメント {comment.html_url} が未 Resolve"
