"""「子storyPR作成」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import issue, label_names

INTAKE_TITLE = "タスク編集機能"
INTAKE_BODY = "既存タスクを編集・削除できる機能を追加する。"

EPIC_TITLE = "タスク編集機能"
EPIC_BRANCH = "feat/epic/task-edit-{number}/base"

# UC 数分の作成を確認するため、ユースケース一覧は 2 行にする
EPIC_PR_BODY = """## 紐づく Issue

- #{intake_number}

## 概要

既存タスクを一覧から選択して編集・削除できる機能を提供する。

## 背景

現状はタスクの新規作成のみで、内容の修正も取り消しもできない。

## ユースケース一覧

| ユースケース | 変更種別 | 概要 | 対応 story | 補足 |
| --- | --- | --- | --- | --- |
| タスク編集 | 変更 | 一覧から編集画面へ遷移して編集内容を保存する | 未作成 | - |
| タスク削除 | 新規 | 一覧から対象タスクを削除する | 未作成 | - |

## 横断要件

| カテゴリ | 要件 | 対象 UC | 補足 |
| --- | --- | --- | --- |
| 既存 API | 保存・削除ともに既存 API を利用する | 全 UC | - |

## タスク一覧

- [x] 複合ユースケースシナリオを作成
"""

WRITER_REPORT = """> from: @complex-scenario-writer
> to: @epic-conductor

複合ユースケースシナリオの作成が完了しました。

| ファイル | 内容 |
| --- | --- |
| `設計図/シナリオ/複合ユースケース/タスク編集から一覧反映.md` | タスク編集 → 一覧反映の業務フロー |

ユースケース一覧の 2 件（タスク編集 / タスク削除）に対応するシナリオが揃っています。
子 story PR の作成をお願いします。

------
"""


def test_normal(
    monitor, gh_live, repo_ctx, issue_factory, layer_pr_factory, wait_until
):
    """完了報告の受領 → UC 数分の子 story PR 作成 → 対応 story 列の反映を確認する（正常系）。"""
    owner, repo = repo_ctx

    # 準備: 起点の intake Issue と、ユースケース一覧 確定済みの epic PR
    intake = issue_factory(
        title=INTAKE_TITLE, body=INTAKE_BODY, labels=["layer:intake", "type:feat"]
    )
    epic_branch = EPIC_BRANCH.format(number=intake.number)
    epic_pr = layer_pr_factory(
        epic_branch, EPIC_TITLE, EPIC_PR_BODY.format(intake_number=intake.number),
        labels=["layer:epic", "type:feat"],
    )

    # 準備: complex-scenario-writer の完了報告 → 確認ラベル付与（起動トリガー）
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=epic_pr.number, body=WRITER_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=epic_pr.number, labels=["確認:epic-conductor"]
    )

    # 実行: 子storyPR作成 の完了を待つ（確認:* 除去 + epic ブランチ上の子 PR）
    def _created():
        data = issue(gh_live, owner, repo, epic_pr.number)
        if any(name.startswith("確認:") for name in label_names(data)):
            return None
        stories = list(
            gh_live.rest.pulls.list(
                owner=owner, repo=repo, state="open", base=epic_branch, per_page=100
            ).parsed_data
        )
        return (data, stories) if stories else None

    data, stories = wait_until(
        _created, timeout_sec=1800, message="子storyPR作成の完了（確認:* 除去 + 子 PR）"
    )

    # 検証: ユースケース一覧の行数と同数の story PR が epic ブランチの上に作られている
    assert len(stories) == 2, f"UC 2 件に対し story PR が {len(stories)} 件: {[s.title for s in stories]}"
    for story in stories:
        assert story.base.ref == epic_branch, (
            f"#{story.number} の base が epic ブランチでない: {story.base.ref}"
        )
        assert story.draft, f"#{story.number} が Draft でない"
        names = label_names(issue(gh_live, owner, repo, story.number))
        assert "layer:story" in names, f"#{story.number} に layer:story がない: {sorted(names)}"
        assert "確認:story-conductor" in names, (
            f"#{story.number} に 確認:story-conductor がない: {sorted(names)}"
        )
        assert "リバースエンジニアリング" not in names, (
            f"#{story.number} に親に無い リバースエンジニアリング が付いている"
        )

    # 検証: 対応 story 列の 未作成 が全て #番号 に置き換わっている
    body = (data.body or "").replace("\r\n", "\n")
    assert "未作成" not in body, "対応 story 列に 未作成 が残っている"
    for story in stories:
        assert f"#{story.number}" in body, f"対応 story 列に #{story.number} が反映されていない"

    # 検証: epic PR は layer 系のみで、議論中 / assignee なし（ユーザー承認なしの自動完了）
    names = label_names(data)
    assert "layer:epic" in names, f"layer:epic がない: {sorted(names)}"
    assert "議論中" not in names, f"議論中 が付与されている: {sorted(names)}"
    assert not data.assignees, "assignee が設定されている"

    # 検証: 完了報告コメントが Resolve 済み
    assert server._is_minimized(report.node_id), "complex-scenario-writer の完了報告が未 Resolve"
