"""「子story起票」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import issue, label_names

INTAKE_TITLE = "タスク編集機能"
INTAKE_BODY = "既存タスクを編集・削除できる機能を追加する。"

EPIC_TITLE = "タスク編集機能"
# UC 数分の起票を確認するため、ユースケース一覧は 2 行にする
EPIC_BODY = """## 前提条件

なし

## 概要

既存タスクを一覧から選択して編集・削除できる機能を提供する。

## 背景

現状はタスクの新規作成のみで、内容の修正も取り消しもできない。

## ユースケース一覧

| UC 名 | 概要 | 対応 story |
| --- | --- | --- |
| タスク編集 | 一覧から編集画面へ遷移して編集内容を保存する | 未起票 |
| タスク削除 | 一覧から対象タスクを削除する | 未起票 |

## 横断要件

- 保存・削除ともに既存 API を利用する
"""

WRITER_REPORT = """> from: @complex-scenario-writer
> to: @epic-conductor

複合ユースケースシナリオの作成が完了しました。

| ファイル | 内容 |
| --- | --- |
| `設計図/シナリオ/複合ユースケース/タスク編集から一覧反映.md` | タスク編集 → 一覧反映の業務フロー |

ユースケース一覧の 2 件（タスク編集 / タスク削除）に対応するシナリオが揃っています。
子 story の起票をお願いします。
"""


def test_normal(monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, wait_until):
    """完了報告の受領 → UC 数分の子 story 起票 → 対応 story 列の反映を確認する（正常系）。"""
    owner, repo = repo_ctx
    # 準備: ユースケース一覧 確定済みの epic Issue + epic Draft PR
    intake, epic = epic_issue_factory(
        INTAKE_TITLE, INTAKE_BODY, EPIC_TITLE, epic_body=EPIC_BODY, epic_labels=["layer:epic", "type:feat"]
    )
    epic_pr_factory(
        branch=f"feat/epic/task-edit-{epic.number}", title=EPIC_TITLE,
        body=f"## 紐づく Issue\n\n- #{epic.number}\n",
    )
    # 準備: complex-scenario-writer の完了報告 → 確認ラベル付与（起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic.number, body=WRITER_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=epic.number, labels=["確認:epic-conductor"]
    )

    # 実行: 子story起票 の完了を待つ（確認:* 除去 + Sub-issue 起票）
    def _created():
        data = issue(gh_live, owner, repo, epic.number)
        if any(name.startswith("確認:") for name in label_names(data)):
            return None
        subs = gh_live.rest.issues.list_sub_issues(
            owner=owner, repo=repo, issue_number=epic.number
        ).parsed_data
        return (data, subs) if subs else None

    data, stories = wait_until(_created, timeout_sec=1800, message="子story起票の完了（確認:* 除去 + 起票）")

    # 検証: ユースケース一覧の行数と同数の story が起票されている
    assert len(stories) == 2, f"UC 2 件に対し story が {len(stories)} 件: {[s.title for s in stories]}"
    for story in stories:
        names = label_names(story)
        assert "layer:story" in names, f"#{story.number} に layer:story がない: {sorted(names)}"
        assert "確認:story-conductor" in names, (
            f"#{story.number} に 確認:story-conductor がない: {sorted(names)}"
        )

    # 検証: 対応 story 列の 未起票 が全て #番号 に置き換わっている
    body = (data.body or "").replace("\r\n", "\n")
    assert "未起票" not in body, "対応 story 列に 未起票 が残っている"
    for story in stories:
        assert f"#{story.number}" in body, f"対応 story 列に #{story.number} が反映されていない"

    # 検証: epic Issue は layer 系のみで、議論中 / assignee なし（ユーザー承認なしの自動完了）
    names = label_names(data)
    assert "layer:epic" in names, f"layer:epic がない: {sorted(names)}"
    assert "議論中" not in names, f"議論中 が付与されている: {sorted(names)}"
    assert not data.assignees, "assignee が設定されている"

    # 検証: 完了報告コメントが Resolve 済み
    assert server._is_minimized(report.node_id), "complex-scenario-writer の完了報告が未 Resolve"
