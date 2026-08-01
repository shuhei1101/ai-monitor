"""「マージ起動」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments_from, issue, label_names
from tests.e2e.実装対象 import (
    IMPLEMENTED_SERVICE_PY,
    PROJECT_FILES,
    RED_TEST_PATH,
    RED_TEST_PY,
    setup_subsystem,
)

# 実装レビューまで完了した状態の subsystem PR 本文（タスク一覧は全チェック済み）
DONE_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [x] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [x] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [x] `update_task` を実装
- [x] 単体テストを追加
- [x] 単体テストを実行

## 単体テスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/tasks/test_service.py` | 全実行 | ✅ | 6 ケース |

## 結合テスト結果

なし

## 単一ユースケースシナリオテスト結果

なし

## 複合ユースケースシナリオテスト結果

なし
"""

ARCHITECT_DONE_REPORT = """> from: @architect
> to: @subsystem-conductor

設計〜実装レビューの一式が完了しました。

| 工程 | 結果 |
| --- | --- |
| SS 設計 | 確定済み（結合 / モジュール構成とも commit 済み） |
| テストレビュー | 指摘なし |
| 実装レビュー | 指摘なし・単体テスト 6 ケース全 pass |

タスク一覧は全てチェック済みです。マージの起動をお願いします。

------
"""

def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until,
):
    """一式完了報告の受領 → ユーザー最終確認ゲートを開くまでを実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=DONE_PR_BODY,
    )
    # 準備: 実装・テストが揃った状態を subsystem ブランチへ積む
    files = {
        **PROJECT_FILES,
        "src/tasks/service.py": IMPLEMENTED_SERVICE_PY,
        "tests/tasks/__init__.py": "",
        RED_TEST_PATH: RED_TEST_PY,
    }
    for path, content in files.items():
        commit_file(ctx["subsystem_branch"], path, content, f"chore: e2e 用に {path} を配置")
    pr_number = ctx["pr"].number
    # 準備: Ready 化 + architect の一式完了報告 → 確認ラベル付与（起動トリガー）
    gh_live.rest.pulls.update(owner=owner, repo=repo, pull_number=pr_number, draft=False)
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number, body=ARCHITECT_DONE_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=["確認:subsystem-conductor"]
    )

    # 実行: 最終確認ゲート（議論中 + assignee）が開くのを待つ
    def _gate_opened():
        data = issue(gh_live, owner, repo, pr_number)
        names = label_names(data)
        if "議論中" not in names or not data.assignees:
            return None
        requests = comments_from(gh_live, owner, repo, pr_number, "subsystem-conductor")
        return (data, requests[-1]) if requests else None

    data, request = wait_until(
        _gate_opened, timeout_sec=1800, message="マージ前の最終確認ゲート（議論中 + assignee）"
    )

    # 検証: タスク一覧が全チェック済みのまま保たれている
    body = (data.body or "").replace("\r\n", "\n")
    task_lines = [
        line for line in body.split("## タスク一覧", 1)[1].split("\n## ", 1)[0].splitlines()
        if line.strip().startswith("- [")
    ]
    assert task_lines, "タスク一覧の行がない"
    assert all(line.strip().startswith("- [x]") for line in task_lines), (
        f"タスク一覧に未チェックが残っている: {task_lines}"
    )

    # 検証: 一式完了報告が Resolve 済みで、最終確認の依頼コメントが投稿されている
    assert server._is_minimized(report.node_id), "architect の一式完了報告が未 Resolve"
    assert request.node_id != report.node_id, "最終確認の依頼コメントが投稿されていない"

    # 検証: 確認:subsystem-conductor は保持されたまま（承認後のマージ実行で復帰する）
    names = label_names(data)
    assert "確認:subsystem-conductor" in names, (
        f"確認:subsystem-conductor が保持されていない: {sorted(names)}"
    )
