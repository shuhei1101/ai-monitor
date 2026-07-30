"""「設計差し戻しからの設計修正」の E2E テスト。"""
from __future__ import annotations

import re

from githubkit.exception import RequestFailed

import ai_monitor.mcp.server as server
from tests.e2e.実装対象 import (
    IMPL_CONFLICT_MODULE_MD,
    MODULE_PATH,
    SUBSYSTEM_PR_BODY,
    TESTER_CONFLICT_MODULE_MD,
    add_worktree,
    branch_sha,
    run_branch_tests,
    seed_subsystem_branch,
    setup_subsystem,
)

# tester がテスト結果表を新設済みの subsystem PR 本文（実装の差し戻し用）
IMPL_PR_BODY = """## 紐づく Issue

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

TESTER_ASSIGN_COMMENT = """> from: @architect
> to: @tester

設計 Wiki が確定したので、テスト作成をお願いします。

確定した設計ページ:
- `docs/wiki/設計図/インターフェース定義/バックエンド/タスク更新.py.md`
- `docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md`

テスト観点の起点は上記 2 ページです。モジュール構成の `#### 単体テスト` 表と、結合の `## 正常系` / `## 異常系` を漏れなくケース化してください。

---
"""

IMPL_ASSIGN_COMMENT = """> from: @architect
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

# 修正 commit の ID（短縮 sha / フル sha / commit URL のいずれの書式でも拾える）
SHA_PATTERN = re.compile(r"\b[0-9a-f]{7,40}\b")


def _issue(gh_live, owner, repo, number):
    """Issue / PR の最新スナップショットを返す。"""
    return gh_live.rest.issues.get(owner=owner, repo=repo, issue_number=number).parsed_data


def _label_names(data) -> set[str]:
    """スナップショットのラベル名集合を返す。"""
    return {label.name for label in data.labels}


def _comments(gh_live, owner, repo, number):
    """Issue / PR のコメント一覧を返す。"""
    return gh_live.rest.issues.list_comments(owner=owner, repo=repo, issue_number=number).parsed_data


def _approve(gh_live, owner, repo, number, assignees) -> None:
    """ユーザー役の承認操作を再現する（議論中 除去 + assignee 外し）。"""
    try:
        gh_live.rest.issues.remove_label(owner=owner, repo=repo, issue_number=number, name="議論中")
    except RequestFailed:
        pass
    for assignee in assignees:
        gh_live.rest.issues.remove_assignees(
            owner=owner, repo=repo, issue_number=number, assignees=[assignee.login]
        )


def _confirm_labels(labels: set[str]) -> list[str]:
    """確認ラベルだけを抜き出す（多重に残っていないことの検証用）。"""
    return sorted(label for label in labels if label.startswith("確認:"))


def _assert_bounce_thread(thread_body: str, worker: str) -> None:
    """差し戻しスレッドに architect の修正内容（commit ID）と worker 宛の再開指示が並ぶことを検証する。"""
    assert thread_body.lstrip().startswith(f"> from: @{worker}"), (
        f"スレッドの起点が {worker} の差し戻し報告でない"
    )
    replies = thread_body.count("> from: @architect")
    assert replies >= 2, f"architect の返信追記が修正内容 + 再開指示の 2 件そろっていない（{replies} 件）"
    assert f"> to: @{worker}" in thread_body, f"再開指示（@{worker} 宛）が返信追記されていない"
    # 修正内容の返信より後ろに commit の ID が含まれていること
    after_first_reply = thread_body.split("> from: @architect", 1)[1]
    assert SHA_PATTERN.search(after_first_reply), "修正 commit の ID が返信追記に含まれていない"


def test_normal_when_test_bounce(
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
    """tester の設計差し戻し → 設計修正（ユーザー承認）→ テスト再作成の循環を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=SUBSYSTEM_PR_BODY,
    )
    # テストの構造が設計から決められないモジュール構成を積む（tester の差し戻しを誘発）
    seed_sha = seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        design_overrides={MODULE_PATH: TESTER_CONFLICT_MODULE_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])

    # 準備: architect のテスト作成の割り当て → 確認:tester 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=TESTER_ASSIGN_COMMENT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:tester"]
    )

    # 実行: tester の設計差し戻しを待つ（確認:architect 付与 + 確認:tester 除去 + 差し戻し報告）
    def _bounced():
        data = _issue(gh_live, owner, repo, ctx["pr"].number)
        labels = _label_names(data)
        if "確認:architect" not in labels or "確認:tester" in labels:
            return None
        bounce = next(
            (c for c in _comments(gh_live, owner, repo, ctx["pr"].number)
             if (c.body or "").lstrip().startswith("> from: @tester")),
            None,
        )
        return (data, bounce) if bounce else None

    bounced, bounce = wait_until(
        _bounced, timeout_sec=1800, message="tester の設計差し戻し（確認:architect 付与 + 差し戻し報告）"
    )

    # 検証: 差し戻し時点では確認ラベルが architect の 1 つだけ
    assert _confirm_labels(_label_names(bounced)) == ["確認:architect"], (
        f"差し戻し時点の確認ラベルが 1 つでない: {_confirm_labels(_label_names(bounced))}"
    )

    # 実行: architect の設計修正 → ユーザー確認待ちを待つ（議論中 + assignee）
    # ここでゲートが開くこと自体が、テスト作成の完了ではなく差し戻しだったことの裏付けになる
    # （テストレビューはユーザーとのやり取りを持たない）
    def _design_gate():
        data = _issue(gh_live, owner, repo, ctx["pr"].number)
        labels = _label_names(data)
        return data if "議論中" in labels and data.assignees else None

    gate = wait_until(
        _design_gate, timeout_sec=1800, message="設計修正のユーザー確認ゲート（議論中 + assignee）"
    )

    # 検証: 確認:architect は保持されたまま（承認後の再開指示で復帰するため）
    assert "確認:architect" in _label_names(gate), "設計修正の待機中に 確認:architect が外れている"

    # 検証: 設計 Wiki の修正 commit がユーザー承認より前に積まれている
    design_fix_sha = branch_sha(gh_live, owner, repo, ctx["subsystem_branch"])
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{design_fix_sha}"
    ).parsed_data
    design_changes = [
        f.filename for f in (compare.files or []) if f.filename.startswith("docs/wiki/設計図/")
    ]
    assert design_changes, "設計 Wiki の修正 commit が積まれていない"

    # 準備: ユーザー承認（議論中 除去 + assignee 外し）
    _approve(gh_live, owner, repo, ctx["pr"].number, gate.assignees)

    # 実行: 再開指示 → テスト再作成の完了を待つ（差し戻しとは別の tester コメントが終端の目印）
    def _recreated():
        data = _issue(gh_live, owner, repo, ctx["pr"].number)
        labels = _label_names(data)
        if "確認:architect" not in labels or "確認:tester" in labels:
            return None
        comments = _comments(gh_live, owner, repo, ctx["pr"].number)
        reports = [
            c for c in comments
            if (c.body or "").lstrip().startswith("> from: @tester") and c.node_id != bounce.node_id
        ]
        if not reports:
            return None
        return data, comments, reports[-1], branch_sha(gh_live, owner, repo, ctx["subsystem_branch"])

    data, comments, report, converged_sha = wait_until(
        _recreated, timeout_sec=2400, message="設計修正後のテスト再作成（tester の完了報告）"
    )

    # 検証: 差し戻しスレッドに修正内容 + 再開指示が並び、tester の処理で Resolve 済み
    thread = next((c for c in comments if c.node_id == bounce.node_id), None)
    assert thread is not None, "tester の差し戻し報告コメントが見つからない"
    _assert_bounce_thread(thread.body or "", "tester")
    assert server._is_minimized(bounce.node_id), "差し戻しスレッドが Resolve されていない"

    # 検証: 修正後の設計 Wiki に基づくテストコードが積まれている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{design_fix_sha}...{converged_sha}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    test_files = [
        f for f in changed
        if f.startswith("tests/") and f.endswith(".py") and not f.endswith("__init__.py")
    ]
    assert test_files, f"設計修正後のテストコードが積まれていない: {changed}"

    # 検証: テスト結果表にテストファイル名の行がある
    body = (data.body or "").replace("\r\n", "\n")
    assert "## 単体テスト結果" in body, "PR 本文に ## 単体テスト結果 がない"
    assert any(f in body for f in test_files), f"テスト結果表にテストファイル名がない: {test_files}"

    # 検証: テストは Red のまま（実装は implementer の領分）
    result = run_branch_tests(sandbox["local_path"], ctx["subsystem_branch"], ref=converged_sha)
    assert result.returncode != 0, "テストが Red になっていない（実装が混入した可能性）"

    # 検証: 完了報告が未 Resolve で投稿され、確認ラベルは architect の 1 つだけ
    assert not server._is_minimized(report.node_id), "完了報告が Resolve されている（Resolve は architect の担当）"
    assert _confirm_labels(_label_names(data)) == ["確認:architect"], (
        f"確認ラベルが多重に残っている: {_confirm_labels(_label_names(data))}"
    )
    assert "議論中" not in _label_names(data), "議論中 が残っている"


def test_normal_when_impl_bounce(
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
    """implementer の設計差し戻し → 設計修正（ユーザー承認）→ 実装再開と実装レビューの通過を実環境で確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=IMPL_PR_BODY,
    )
    # レビュー済みの Red テストと、実装が設計から決められないモジュール構成を積む
    seed_sha = seed_subsystem_branch(
        gh_live, owner, repo, commit_file, ctx["subsystem_branch"],
        with_red_test=True, design_overrides={MODULE_PATH: IMPL_CONFLICT_MODULE_MD},
    )
    add_worktree(sandbox["local_path"], ctx["subsystem_branch"])

    # 準備: architect の実装の割り当て → 確認:implementer 付与（起動トリガー）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=IMPL_ASSIGN_COMMENT
    )
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:implementer"]
    )

    # 実行: implementer の設計差し戻しを待つ（確認:architect 付与 + 確認:implementer 除去 + 差し戻し報告）
    def _bounced():
        data = _issue(gh_live, owner, repo, ctx["pr"].number)
        labels = _label_names(data)
        if "確認:architect" not in labels or "確認:implementer" in labels:
            return None
        bounce = next(
            (c for c in _comments(gh_live, owner, repo, ctx["pr"].number)
             if (c.body or "").lstrip().startswith("> from: @implementer")),
            None,
        )
        return (data, bounce) if bounce else None

    bounced, bounce = wait_until(
        _bounced, timeout_sec=1800, message="implementer の設計差し戻し（確認:architect 付与 + 差し戻し報告）"
    )

    # 検証: 差し戻し時点では確認ラベルが architect の 1 つだけ
    assert _confirm_labels(_label_names(bounced)) == ["確認:architect"], (
        f"差し戻し時点の確認ラベルが 1 つでない: {_confirm_labels(_label_names(bounced))}"
    )

    # 検証: Draft のまま（差し戻しで自ターンを終えている）
    pr_bounced = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=ctx["pr"].number).parsed_data
    assert pr_bounced.draft is True, "Draft が解除されている（差し戻しではなく実装が完了した可能性）"

    # 実行: architect の設計修正 → ユーザー確認待ちを待つ（議論中 + assignee）
    def _design_gate():
        data = _issue(gh_live, owner, repo, ctx["pr"].number)
        labels = _label_names(data)
        return data if "議論中" in labels and data.assignees else None

    gate = wait_until(
        _design_gate, timeout_sec=1800, message="設計修正のユーザー確認ゲート（議論中 + assignee）"
    )
    assert "確認:architect" in _label_names(gate), "設計修正の待機中に 確認:architect が外れている"

    # 検証: 設計 Wiki の修正 commit がユーザー承認より前に積まれている
    design_fix_sha = branch_sha(gh_live, owner, repo, ctx["subsystem_branch"])
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{seed_sha}...{design_fix_sha}"
    ).parsed_data
    design_changes = [
        f.filename for f in (compare.files or []) if f.filename.startswith("docs/wiki/設計図/")
    ]
    assert design_changes, "設計 Wiki の修正 commit が積まれていない"

    # 準備: ユーザー承認（議論中 除去 + assignee 外し）
    _approve(gh_live, owner, repo, ctx["pr"].number, gate.assignees)

    # 実行: 再開指示 → 実装 → 実装レビュー通過（確認:subsystem-conductor 付与）まで待つ
    def _handed_off():
        data = _issue(gh_live, owner, repo, ctx["pr"].number)
        labels = _label_names(data)
        if "確認:subsystem-conductor" not in labels:
            return None
        comments = _comments(gh_live, owner, repo, ctx["pr"].number)
        # ラベル付与と一式完了報告の投稿は別呼び出しなので、両方そろうまで待つ
        if not [
            c for c in comments
            if (c.body or "").lstrip().startswith("> from: @architect")
            and "> to: @subsystem-conductor" in (c.body or "")
        ]:
            return None
        return data, comments, branch_sha(gh_live, owner, repo, ctx["subsystem_branch"])

    data, comments, converged_sha = wait_until(
        _handed_off, timeout_sec=3600, message="実装レビュー通過（確認:subsystem-conductor + 一式完了報告）"
    )

    # 検証: 差し戻しスレッドに修正内容 + 再開指示が並び、implementer の処理で Resolve 済み
    thread = next((c for c in comments if c.node_id == bounce.node_id), None)
    assert thread is not None, "implementer の差し戻し報告コメントが見つからない"
    _assert_bounce_thread(thread.body or "", "implementer")
    assert server._is_minimized(bounce.node_id), "差し戻しスレッドが Resolve されていない"

    # 検証: 修正後の設計 Wiki に基づく実装 commit が積まれている
    compare = gh_live.rest.repos.compare_commits(
        owner=owner, repo=repo, basehead=f"{design_fix_sha}...{converged_sha}"
    ).parsed_data
    changed = [f.filename for f in (compare.files or [])]
    assert any(f.startswith("src/") for f in changed), f"設計修正後の実装 commit がない: {changed}"

    # 検証: テストが Green・PR が Ready
    result = run_branch_tests(sandbox["local_path"], ctx["subsystem_branch"], ref=converged_sha)
    assert result.returncode == 0, f"テストが Green になっていない:\n{result.stderr[-1500:]}"
    pr_now = gh_live.rest.pulls.get(owner=owner, repo=repo, pull_number=ctx["pr"].number).parsed_data
    assert pr_now.draft is False, "PR が Draft のまま（Draft 解除は implementer の担当）"

    # 検証: テスト結果表が全 ✅ + タスク一覧が全チェック済み
    body = (data.body or "").replace("\r\n", "\n")
    result_rows = [line for line in body.splitlines() if line.startswith("| `tests/")]
    assert result_rows, "テスト結果表にテストファイルの行がない"
    for row in result_rows:
        assert "✅" in row, f"テスト結果表が全 ✅ でない: {row}"
    assert "- [ ]" not in body, "タスク一覧に未チェックの行が残っている"

    # 検証: subsystem-conductor 宛の一式完了報告が未 Resolve で投稿されている
    handoffs = [
        c for c in comments
        if (c.body or "").lstrip().startswith("> from: @architect")
        and "> to: @subsystem-conductor" in (c.body or "")
    ]
    assert handoffs, "architect の一式完了報告コメントが投稿されていない"
    assert not server._is_minimized(handoffs[-1].node_id), (
        "一式完了報告が Resolve されている（受領は subsystem-conductor の担当）"
    )

    # 検証: 確認ラベルが subsystem-conductor の 1 つだけ
    assert _confirm_labels(_label_names(data)) == ["確認:subsystem-conductor"], (
        f"確認ラベルが多重に残っている: {_confirm_labels(_label_names(data))}"
    )
