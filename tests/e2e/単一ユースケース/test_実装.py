"""「実装」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import supplement_review_comments
from tests.e2e.実装対象 import (
    RED_TEST_PATH,
    run_branch_tests,
    seed_subsystem_branch,
    setup_subsystem,
)

# tester が作成済みの状態を再現する（テスト結果表の行あり・結果列は未記入）
SUBSYSTEM_PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] `update_task` を実装
- [ ] 単体テストを作成して実行

## 単体テスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/tasks/test_service.py` | 全実行 | | 6 ケース（正常 2 / 異常 4） |

## 結合テスト結果

なし
"""

ASSIGN_COMMENT = """> from: @architect
> to: @implementer

テストレビューが完了したので、実装をお願いします。

Red のテストファイル:
- `tests/tasks/test_service.py`

実装の根拠になる設計ページ:
- `docs/wiki/設計図/インターフェース定義/バックエンド/タスク更新.py.md`
- `docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md`

モジュール構成の `#### 処理` の各ステップを関数内のコメントとして残してください。

---
"""


def test_normal(
    monitor,
    gh_live,
    repo_ctx,
    epic_issue_factory,
    epic_pr_factory,
    draft_pr_factory,
    story_issue_factory,
    subsystem_issue_factory,
    commit_file,
    wait_until,
    sandbox,
):
    """タスク一覧の消化とテストの Green 化・Draft 解除・完了報告を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    seed_sha = seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"], with_red_test=True
    )

    # 準備: architect の実装の割り当て → 確認:implementer 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=ASSIGN_COMMENT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:implementer"]
    )

    # 実行: 実装の完了を待つ（確認:implementer 除去 + 確認:architect 付与）
    def _done():
        data = gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=ctx["pr"].number).parsed_data
        labels = {label.name for label in data.labels}
        if "確認:architect" not in labels or "確認:implementer" in labels:
            return None
        return data

    data = wait_until(_done, timeout_sec=1800, message="実装の完了（確認:architect 付与 + 確認:implementer 除去）")

    # 検証: テスト結果表の結果列が全て ✅
    body = (data.body or "").replace("\r\n", "\n")
    assert "## 単体テスト結果" in body, "PR 本文に ## 単体テスト結果 がない"
    result_rows = [
        line for line in body.splitlines()
        if line.startswith("| `tests/") or line.startswith("| tests/")
    ]
    assert result_rows, "テスト結果表にテストファイルの行がない"
    for row in result_rows:
        assert "✅" in row, f"結果列が ✅ で埋まっていない: {row}"

    # 検証: タスク一覧のチェックは未変更（チェックは architect が検収時に入れる）
    assert "- [x]" not in body, "タスク一覧にチェックが入っている"

    # 検証: テストが実際に Green になっている
    result = run_branch_tests(sandbox["local_path"], ctx["subsystem_branch"])
    assert result.returncode == 0, f"テストが Green になっていない:\n{result.stderr[-1500:]}"

    # 検証: PR が Ready（Draft 解除済み）
    pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=ctx["pr"].number).parsed_data
    assert pr_now.draft is False, "PR が Draft のまま（Draft 解除は implementer の担当）"

    # 検証: 実装コードが積まれ、Red テストは書き換えられていない
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{ctx['subsystem_branch']}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert changed, "実装の commit が積まれていない"
    assert any(f.startswith("src/") for f in changed), f"src/ 配下の実装がない: {changed}"
    assert RED_TEST_PATH not in changed, f"Red テストが書き換えられている: {RED_TEST_PATH}"

    # 検証: architect 宛の完了報告が未 Resolve で投稿されている
    comments = gh_live.rest.issues.list_comments(
        owner=owner, repo=repo, issue_number=ctx["pr"].number
    ).parsed_data
    reports = [c for c in comments if (c.body or "").lstrip().startswith("> from: @implementer")]
    assert reports, "implementer の完了報告コメントが投稿されていない"
    assert not server._is_minimized(reports[-1].node_id), "完了報告が Resolve されている（Resolve は architect の担当）"

    # 検証: commit 内容に対する補足事項がインラインコメントで残っている
    assert supplement_review_comments(gh_live, owner, repo, ctx["pr"].number), (
        "補足事項のインラインコメントが投稿されていない"
    )

    # 検証: 議論中 / assignee なし（ユーザーとの会話を持たない）
    labels = {label.name for label in data.labels}
    assert "議論中" not in labels, "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"
