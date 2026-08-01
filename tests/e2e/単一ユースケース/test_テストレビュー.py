"""「テストレビュー」の E2E テスト。"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments, issue, label_names, unresolved_review_threads
from tests.e2e.実装対象 import (
    INCOMPLETE_TEST_PY,
    RED_TEST_PATH,
    RED_TEST_PY,
    seed_subsystem_branch,
    setup_subsystem,
)

PR_BODY = """## 紐づく Issue

- #{subsystem_number}

## タスク一覧

- [ ] `設計図/インターフェース定義/バックエンド/タスク更新.py.md` を新規作成
- [ ] `設計図/モジュール構成/バックエンド/タスク.py.md` を新規作成
- [ ] `update_task` を実装
- [ ] 単体テストを作成して実行

## 単体テスト結果

| ファイル | メソッド | 結果 | 補足 |
| --- | --- | --- | --- |
| `tests/tasks/test_service.py` | 全実行 | | - |

## 結合テスト結果

なし
"""

TESTER_REPORT = """> from: @tester
> to: @architect

テスト作成が完了しました。

- 作成したテストファイル: `tests/tasks/test_service.py`
- 元にした設計ページ: `docs/wiki/設計図/モジュール構成/バックエンド/タスク.py.md`
- 実行結果: 想定どおり fail（`update_task` が未実装のため import エラー）

| commit | 内容 |
| --- | --- |
| seed | 単体テストを追加 |

---
"""


def _setup(gh_live, owner, repo, factories, commit_file, *, test_code: str):
    """テスト作成完了時点の subsystem PR 一式を用意する。"""
    ctx = setup_subsystem(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["draft_pr_factory"],
        factories["story_issue_factory"], factories["subsystem_issue_factory"], commit_file,
        pr_body=PR_BODY,
    )
    seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])
    commit_file(ctx["subsystem_branch"], "tests/tasks/__init__.py", "", "chore: e2e 用のテストパッケージを配置")
    commit_file(ctx["subsystem_branch"], RED_TEST_PATH, test_code, "test: 単体テストを追加")
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=TESTER_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )
    return ctx, report


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory):
    """セットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "subsystem_issue_factory": subsystem_issue_factory,
    }


def _wait_handed_to(gh_live, owner, repo, pr_number, target: str, wait_until, *, message):
    """architect から指定の担当への引き渡し（確認ラベルの入れ替え）を待つ。"""

    def _done():
        data = issue(gh_live, owner, repo, pr_number)
        names = label_names(data)
        if f"確認:{target}" not in names or "確認:architect" in names:
            return None
        return data

    return wait_until(_done, timeout_sec=2400, message=message)


def _test_task_line(body: str) -> str:
    """タスク一覧のテスト作成タスク行を返す。"""
    lines = [line for line in (body or "").replace("\r\n", "\n").splitlines() if "単体テストを作成して実行" in line]
    assert lines, "タスク一覧にテスト作成タスクの行がない"
    return lines[0].strip()


def test_normal(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """設計 Wiki どおりのテストを指摘なしで通し implementer へ委任することを確認する（正常系）。"""
    owner, repo = repo_ctx
    ctx, report = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, test_code=RED_TEST_PY,
    )

    data = _wait_handed_to(
        gh_live, owner, repo, ctx["pr"].number, "implementer", wait_until, message="テストレビュー通過",
    )

    # 検証: 未解決のインライン指摘スレッドが残っていない
    unresolved = unresolved_review_threads(gh_live, owner, repo, ctx["pr"].number)
    assert not unresolved, f"未解決のインライン指摘スレッドが残っている: {unresolved}"

    # 検証: 完了報告スレッドにレビュー結果が返信追記され、Resolve 済み
    thread = next(c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id)
    assert "> from: @architect" in (thread.body or ""), "レビュー結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "完了報告スレッドが Resolve されていない"

    # 検証: タスク一覧のテスト作成タスクがチェック済み
    assert _test_task_line(data.body).startswith("- [x]"), (
        f"テスト作成タスクが未チェック: {_test_task_line(data.body)}"
    )


def test_error_when_pointed_out(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """設計 Wiki の単体テスト表との不整合を指摘して tester へ差し戻すことを確認する（異常系・テストへの指摘あり）。"""
    owner, repo = repo_ctx
    ctx, report = _setup(
        gh_live, owner, repo,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, subsystem_issue_factory),
        commit_file, test_code=INCOMPLETE_TEST_PY,
    )

    data = _wait_handed_to(
        gh_live, owner, repo, ctx["pr"].number, "tester", wait_until, message="指摘の投稿と tester への差し戻し",
    )

    # 検証: インライン指摘が投稿されている
    assert gh_live.rest.pulls.list_review_comments(
        owner=owner, repo=repo, pull_number=ctx["pr"].number
    ).parsed_data, "インライン指摘が投稿されていない（指摘なしで通過した可能性）"

    # 検証: 完了報告スレッドに対応依頼が返信追記され、未解決のまま残っている
    thread = next(c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id)
    assert "> to: @tester" in (thread.body or ""), "対応依頼が返信追記されていない"
    assert not server._is_minimized(report.node_id), (
        "完了報告スレッドが Resolve されている（修正確定まで同スレッドで往復する）"
    )

    # 検証: タスク一覧のテスト作成タスクは未チェックのまま
    assert _test_task_line(data.body).startswith("- [ ]"), (
        f"テスト作成タスクがチェックされている: {_test_task_line(data.body)}"
    )


# 実装済み（タスク一覧の実装タスクがチェック済み）の PR 本文
IMPLEMENTED_PR_BODY = PR_BODY.replace("- [ ] `update_task` を実装", "- [x] `update_task` を実装")

# 実装レビューでテストコード側の問題と判定して tester へ差し戻した記録
BOUNCE_RECORD = """> from: @architect
> to: @tester

実装レビューの結果、fail の原因はテストコード側でした。

- 実装は設計どおりで変更不要（`src/tasks/service.py` は現状のまま）
- テストの期待値が設計の単体テスト表と食い違っているため、テスト側を修正してください

---
"""

# 差し戻しを受けた tester の修正完了報告（本ケースの起動条件）
RETEST_REPORT = """> from: @tester
> to: @architect

差し戻しを受けてテストコードを修正しました。

- 修正したテストファイル: `tests/tasks/test_service.py`
- 実装は変更していません
- 実行結果: 全 pass

| commit | 内容 |
| --- | --- |
| seed | 単体テストの期待値を設計に合わせて修正 |

---
"""


def test_normal_when_after_implementation(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, subsystem_issue_factory, commit_file, wait_until, sandbox,
):
    """実装済みの状態でのテスト再レビューと一式完了報告を確認する（正常系・実装後の再レビュー）。"""
    from tests.e2e.実装対象 import IMPLEMENTED_SERVICE_PY

    owner, repo = repo_ctx
    # 準備: 実装タスクがチェック済みの subsystem PR（実装コードは修正前のまま）
    ctx = setup_subsystem(
        gh_live, owner, repo,
        epic_issue_factory, epic_pr_factory, draft_pr_factory,
        story_issue_factory, subsystem_issue_factory, commit_file,
        pr_body=IMPLEMENTED_PR_BODY,
    )
    seed_subsystem_branch(gh_live, owner, repo, commit_file, ctx["subsystem_branch"])
    commit_file(ctx["subsystem_branch"], "tests/tasks/__init__.py", "", "chore: e2e 用のテストパッケージを配置")
    commit_file(ctx["subsystem_branch"], RED_TEST_PATH, RED_TEST_PY, "test: 単体テストを追加")
    commit_file(
        ctx["subsystem_branch"], "src/tasks/service.py", IMPLEMENTED_SERVICE_PY, "feat: update_task を実装"
    )
    service_sha_before = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path="src/tasks/service.py", ref=ctx["subsystem_branch"]
    ).parsed_data.sha

    # 準備: 差し戻しの経緯 + tester の修正完了報告（起動条件）
    gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=BOUNCE_RECORD
    )
    report = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, body=RETEST_REPORT
    ).parsed_data
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=ctx["pr"].number, labels=["確認:architect"]
    )

    # 実行: subsystem-conductor への一式完了報告（確認ラベルの入れ替え）を待つ
    data = _wait_handed_to(
        gh_live, owner, repo, ctx["pr"].number, "subsystem-conductor", wait_until,
        message="実装後の再レビュー通過（確認:subsystem-conductor 付与）",
    )

    # 検証: 修正完了報告スレッドにレビュー結果が返信追記され Resolve 済み
    thread = next(c for c in comments(gh_live, owner, repo, ctx["pr"].number) if c.node_id == report.node_id)
    assert "> from: @architect" in (thread.body or ""), "レビュー結果が返信追記されていない"
    assert server._is_minimized(report.node_id), "修正完了報告スレッドが Resolve されていない"

    # 検証: 未解決のインライン指摘スレッドが残っていない
    unresolved = unresolved_review_threads(gh_live, owner, repo, ctx["pr"].number)
    assert not unresolved, f"未解決のインライン指摘スレッドが残っている: {unresolved}"

    # 検証: 実装タスクはチェック済みのまま
    impl_line = next(
        line for line in (data.body or "").replace("\r\n", "\n").splitlines()
        if "`update_task` を実装" in line
    )
    assert impl_line.strip().startswith("- [x]"), f"実装タスクのチェックが外れている: {impl_line}"

    # 検証: implementer へ差し戻していない（実装の割り当てコメントなし）
    assigned = [c for c in comments(gh_live, owner, repo, ctx["pr"].number) if "> to: @implementer" in (c.body or "")]
    assert not assigned, f"implementer への割り当てコメントが投稿されている: {[c.html_url for c in assigned]}"

    # 検証: 実装コードが変わっていない
    service_sha_after = gh_live.rest.repos.get_content(
        owner=owner, repo=repo, path="src/tasks/service.py", ref=ctx["subsystem_branch"]
    ).parsed_data.sha
    assert service_sha_after == service_sha_before, "実装コードが変更されている"

    # 検証: 一式完了報告が投稿されている
    reports = [c for c in comments(gh_live, owner, repo, ctx["pr"].number) if "> to: @subsystem-conductor" in (c.body or "")]
    assert reports, "subsystem-conductor 宛の一式完了報告が投稿されていない"
