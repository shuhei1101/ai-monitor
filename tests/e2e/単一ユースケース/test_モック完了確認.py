"""「モック完了確認」の E2E テスト。"""
from __future__ import annotations

import server

INTAKE_TITLE = "タスク期限のメール通知機能"
INTAKE_BODY = "タスクの期限が近づいたらメールで通知する機能を追加したいです。"
EPIC_TITLE = "タスク期限のメール通知機能"

PR_BODY = """## 紐づく Issue

- #{epic_number}

## UI 設計

### 画面一覧

| 画面 | 新規 / 変更 | 概要 |
| --- | --- | --- |
| 通知設定画面 | 新規 | 通知の on/off とタイミングを設定する |

### 画面遷移

設定メニュー → 通知設定画面

### モック

- 通知設定画面: https://raw.githack.example/mock/pages/notification-settings/
"""

MOCK_REPORT = """> from: @mock-designer
> to: @epic-conductor

全体 UI 設計が完了しました。
画面一覧・画面遷移・モック URL を epic PR 本文の `## UI 設計` に反映済みです。
モックはユーザー承認済み（`議論中` 除去確認済み）です。確認後、本コメントの Resolve をお願いします。
"""


def test_normal(monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, epic_body, wait_until):
    """mock-designer の完了報告確認 → complex-scenario-writer への引き継ぎを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: 5 セクション確定済みの epic Issue（確認ラベルはまだ付けない）+ UI 設計入りの epic Draft PR
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=epic_body, epic_labels=["layer:epic"]
    )
    pr = epic_pr_factory(
        branch=f"feat/epic/mock-kanryo-{epic.number}",
        title=EPIC_TITLE,
        body=PR_BODY.format(epic_number=epic.number),
    )

    # 準備: mock-designer の完了報告コメントを投稿してから確認ラベルを付ける（先に付けると初回フェーズが走るため）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic.number, body=MOCK_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(owner=owner, repo=repo, issue_number=epic.number, labels=["確認:epic-conductor"])

    # 実行: モニターの polling 検知 → モック完了確認の完了を待つ（epic PR への引き継ぎラベル）
    def _handed_over():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=pr.number).parsed_data
        labels = {label.name for label in data.labels}
        return data if "確認:complex-scenario-writer" in labels else None

    wait_until(_handed_over, timeout_sec=1200, message="モック完了確認の完了（epic PR に 確認:complex-scenario-writer）")

    # 検証: epic Issue の 確認:* が除去され、議論中なし・assignee なしの自動完了になっている
    issue = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=epic.number).parsed_data
    labels = {label.name for label in issue.labels}
    assert not any(name.startswith("確認:") for name in labels)
    assert "議論中" not in labels
    assert not issue.assignees

    # 検証: mock-designer の完了報告コメントが Resolve 済み
    assert server._is_minimized(report.node_id), "完了報告コメントが未 Resolve"
