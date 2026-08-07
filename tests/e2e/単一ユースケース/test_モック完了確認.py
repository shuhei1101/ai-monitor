"""「モック完了確認」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server

INTAKE_TITLE = "タスク期限のメール通知機能"
INTAKE_BODY = "タスクの期限が近づいたらメールで通知する機能を追加したいです。"
EPIC_TITLE = "タスク期限のメール通知機能"

# モックの成果物 PR 本文（mock-designer が「全体UI設計」を終えた状態）
MOCK_PR_BODY = """## 紐づく Issue

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

## タスク一覧

- [x] 通知設定画面のモックを作成
- [x] `## UI 設計` の画面一覧・画面遷移・モックを記入
"""

MOCK_REPORT = """> from: @mock-designer
> to: @epic-conductor

全体 UI 設計が完了しました。
画面一覧・画面遷移・モック URL を本 PR 本文の `## UI 設計` に反映済みです。
モックはユーザー承認済み（`議論中` 除去確認済み）です。確認後、本コメントの Resolve をお願いします。

------
"""


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    epic_body, wait_until,
):
    """mock-designer の完了報告確認 → complex-scenario-writer への引き継ぎを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: 5 セクション確定済みの epic Issue + 親 intake（面は PR なので確認ラベルは付けない）
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=epic_body, epic_labels=["layer:epic"]
    )
    # 準備: 要件の SoT になる epic ベース PR（確認ラベルなし = 起動対象にしない）
    epic_branch = f"feat/epic/mock-kanryo-{epic.number}/base"
    epic_pr_factory(
        branch=epic_branch,
        title=EPIC_TITLE,
        body=f"## 紐づく Issue\n\n- #{epic.number}\n\n{epic_body}",
    )
    # 準備: 作業対象のモック成果物 PR（base=epic ブランチ）。UI 設計は成果物 PR 本文が持つ
    mock_pr = draft_pr_factory(
        f"docs/epic/mock-kanryo-{epic.number}/mock",
        f"{EPIC_TITLE}（モック）",
        MOCK_PR_BODY.format(epic_number=epic.number),
        base_branch=epic_branch,
    )

    # 準備: mock-designer の完了報告コメントを投稿してから確認ラベルを付ける（先に付けると初回フェーズが走るため）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=mock_pr.number, body=MOCK_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=mock_pr.number, labels=["確認:epic-conductor"]
    )

    # 実行: モニターの polling 検知 → 複合UCシナリオの成果物 PR へ引き継がれるまで待つ
    def _handed_over():
        pulls = gh_live.rest.pulls.list(
            owner=owner, repo=repo, state="open", per_page=100
        ).parsed_data
        # epic ブランチを base に持つ PR のうち、seed したモック PR 以外が引き継ぎ先の候補になる
        for pr in pulls:
            if pr.base.ref != epic_branch or pr.number == mock_pr.number:
                continue
            data = gh_live.rest.issues.get(
                owner=owner, repo=repo, issue_number=pr.number
            ).parsed_data
            if "確認:complex-scenario-writer" in {label.name for label in data.labels}:
                return pr
        return None

    scenario_pr = wait_until(
        _handed_over,
        timeout_sec=1200,
        message="モック完了確認の完了（複合UCシナリオの成果物 PR に 確認:complex-scenario-writer）",
    )

    # 検証: モックの成果物 PR がマージされている
    merged = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=mock_pr.number).parsed_data
    assert merged.merged, "モックの成果物 PR がマージされていない"

    # 検証: 引き継ぎ先の PR 本文が 紐づく Issue + 全行未チェックのタスク一覧になっている
    body = (scenario_pr.body or "").replace("\r\n", "\n")
    sections = [line for line in body.splitlines() if line.startswith("## ")]
    assert sections == ["## 紐づく Issue", "## タスク一覧"], (
        f"シナリオ PR 本文のセクションが 紐づく Issue + タスク一覧 でない: {sections}"
    )
    tasks = [line.strip() for line in body.splitlines() if line.strip().startswith("- [")]
    assert tasks, "タスク一覧に行がない"
    assert all(line.startswith("- [ ]") for line in tasks), (
        f"作成時点でチェック済みの行がある（チェックは各作業者が入れる）: {tasks}"
    )

    # 検証: mock-designer の完了報告コメントが Resolve 済み
    assert server._is_minimized(report.node_id), "完了報告コメントが未 Resolve"
