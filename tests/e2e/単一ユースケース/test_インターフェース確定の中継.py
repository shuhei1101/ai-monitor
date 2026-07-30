"""「インターフェース確定の中継」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments_from, issue, label_names
from tests.e2e.実装対象 import SUBSYSTEM_PR_BODY, setup_subsystem

# 依存順の後続 subsystem が 未起票 で残っている story 本文
STORY_BODY_TEMPLATE = """## 前提条件

なし

## 概要

ユーザーが一覧からタスクを選択して、内容を編集して保存する。

## 背景

親 epic #{epic_number} の UC「タスク編集」に対応。

## ユースケース要件

| 要件 | 補足 |
| --- | --- |
| タスクの内容を編集して保存できる | - |
| 保存時にバリデーションエラーをインライン表示 | タイトルは 1 文字以上 100 文字以内 |

## サブシステム一覧

| scope | 概要 | 依存 | 対応 subsystem |
| --- | --- | --- | --- |
| backend | `update_task` の実装 | なし | 起票済み |
| frontend | 編集画面と保存導線 | backend | 未起票 |
"""

INTERFACE_REPORT = """> from: @architect
> to: @subsystem-conductor

バックエンドのインターフェースが確定しました。

| エンドポイント | 概要 |
| --- | --- |
| `PATCH /tasks/{task_id}` | タイトルと本文を更新して更新後のタスクを返す |

| フィールド | 型 | 必須 | 制限 |
| --- | --- | --- | --- |
| `title` | str | ✅ | 1 文字以上 100 文字以内 |
| `content` | str | - | 1000 文字以内 |

後続の frontend subsystem はこのインターフェースで着手できます。
設計は続行中です。

---
"""


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until,
):
    """インターフェース確定報告の受領 → 親 story への中継を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    # 準備: 後続 subsystem が 未起票 で残っている story 本文にする
    gh_live.rest.issues.update(
        owner=owner, repo=repo, issue_number=ctx["story"].number,
        body=STORY_BODY_TEMPLATE.format(epic_number=ctx["epic"].number),
    )
    pr_number = ctx["pr"].number
    # 準備: 設計続行中（確認:architect 保持）+ architect のインターフェース確定報告
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=["確認:architect"]
    )
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number, body=INTERFACE_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=["確認:subsystem-conductor"]
    )

    # 実行: 中継の完了を待つ（親 story に 確認:story-conductor + 報告コメント）
    def _relayed():
        story_now = issue(gh_live, owner, repo, ctx["story"].number)
        if "確認:story-conductor" not in label_names(story_now):
            return None
        relayed = comments_from(gh_live, owner, repo, ctx["story"].number, "subsystem-conductor")
        if not relayed:
            return None
        pr_now = issue(gh_live, owner, repo, pr_number)
        return (pr_now, relayed[-1]) if "確認:subsystem-conductor" not in label_names(pr_now) else None

    pr_now, relayed = wait_until(
        _relayed, timeout_sec=1800, message="インターフェース確定の中継（確認:story-conductor 付与 + 報告）"
    )

    # 検証: 中継報告が @story-conductor 宛で未解決のまま残っている
    assert "> to: @story-conductor" in (relayed.body or ""), "中継報告の宛先が story-conductor でない"
    assert not server._is_minimized(relayed.node_id), "中継報告が Resolve されている（受領は story-conductor）"

    # 検証: 元のインターフェース確定報告が Resolve 済み
    assert server._is_minimized(report.node_id), "architect のインターフェース確定報告が未 Resolve"

    # 検証: subsystem PR は 確認:architect を保持したまま 確認:subsystem-conductor だけが外れている
    names = label_names(pr_now)
    assert "確認:architect" in names, f"確認:architect が保持されていない: {sorted(names)}"
    assert "確認:subsystem-conductor" not in names, f"確認:subsystem-conductor が残っている: {sorted(names)}"
