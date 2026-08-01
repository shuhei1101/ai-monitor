"""「統合テスト指揮」の E2E テスト。

UC は単一 UC（story レベル）で代表して書かれているが、読み替え先の複合 UC（epic レベル）も
別エージェントの実体なので、両レベルとも実行する。
"""
from __future__ import annotations

import ai_monitor.mcp.server as server
from tests.e2e.エスカレーション import comments_from, issue, label_names
from tests.e2e.実装対象 import add_worktree
from tests.e2e.統合テスト import (
    COMPLEX_E2E_TEST_PY,
    E2E_TEST_PY,
    EPIC_PR_BODY,
    EPIC_PR_BODY_FAILED,
    STORY_PR_BODY,
    STORY_PR_BODY_FAILED,
    complex_result_rows,
    epic_branch_files,
    result_rows,
    setup_epic,
    setup_story,
    story_branch_files,
)

SINGLE = {
    "writer": "single-scenario-writer",
    "tester": "single-scenario-tester",
    "conductor": "story-conductor",
    "e2e_test": E2E_TEST_PY,
    "rows": result_rows,
}
COMPLEX = {
    "writer": "complex-scenario-writer",
    "tester": "complex-scenario-tester",
    "conductor": "epic-conductor",
    "e2e_test": COMPLEX_E2E_TEST_PY,
    "rows": complex_result_rows,
}

SCENARIO_DONE_REPORT = """> from: @{writer}
> to: @{login}

ユースケースシナリオの設計が完了し、ユーザー確認を経て確定しました。

| ファイル | 内容 |
| --- | --- |
| `設計図/シナリオ/` 配下 | 対象シナリオを作成し、索引にも行を追加 |

---
"""


def _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file):
    """レベル別のセットアップに渡す factory 群をまとめる。"""
    return {
        "epic_issue_factory": epic_issue_factory,
        "epic_pr_factory": epic_pr_factory,
        "draft_pr_factory": draft_pr_factory,
        "story_issue_factory": story_issue_factory,
        "commit_file": commit_file,
    }


def _setup(gh_live, owner, repo, level, factories, *, pr_body, e2e_test=None):
    """レベルに応じた統合テスト待機中の PR 一式を用意する。"""
    # story レベルは story ブランチ、epic レベルは epic ブランチへ資材を積む
    if level is SINGLE:
        ctx = setup_story(
            gh_live, owner, repo,
            factories["epic_issue_factory"], factories["epic_pr_factory"],
            factories["draft_pr_factory"], factories["story_issue_factory"], factories["commit_file"],
            pr_body=pr_body, files=story_branch_files(e2e_test=e2e_test),
        )
        ctx["branch"] = ctx["story_branch"]
        ctx["parent_number"] = ctx["story"].number
        return ctx
    ctx = setup_epic(
        gh_live, owner, repo,
        factories["epic_issue_factory"], factories["epic_pr_factory"], factories["commit_file"],
        pr_body=pr_body, files=epic_branch_files(complex_e2e_test=e2e_test),
    )
    ctx["branch"] = ctx["epic_branch"]
    ctx["parent_number"] = ctx["epic"].number
    return ctx


def _seed_finished_scenario_design(gh_live, owner, repo, pr_number, level):
    """シナリオ設計が済んだ状態（Resolve 済みの自身コメントあり）を再現する。

    フェーズ索引では `シナリオ作成（初回）` が「自身の投稿コメントが Resolved 込みで 0 件」で
    マッチするため、統合テスト系のフェーズを起動するには過去の自分コメントが要る。
    """
    login = gh_live.rest.users.get_authenticated().parsed_data.login
    posted = gh_live.rest.issues.create_comment(
        owner=owner, repo=repo, issue_number=pr_number,
        body=SCENARIO_DONE_REPORT.format(writer=level["writer"], login=login),
    ).parsed_data
    server._minimize_comment(posted.node_id)
    return posted


def _start(gh_live, owner, repo, pr_number, level):
    """conductor の委任（確認ラベル付与）を再現する。"""
    gh_live.rest.issues.add_labels(
        owner=owner, repo=repo, issue_number=pr_number, labels=[f"確認:{level['writer']}"]
    )


def _labeled_names(gh_live, owner, repo, number) -> list[str]:
    """PR に付与されたラベル名をタイムラインから時系列で返す。"""
    events = gh_live.rest.issues.list_events_for_timeline(
        owner=owner, repo=repo, issue_number=number, per_page=100
    ).parsed_data
    return [
        getattr(e.label, "name", "") for e in events if getattr(e, "event", "") == "labeled"
    ]


def _run_implement_start(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """正常シナリオ（テスト実装の起動）を実行して検証する。"""
    # 準備: テスト結果表が未記入（セクション自体が無い）の PR
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        pr_body=STORY_PR_BODY if level is SINGLE else EPIC_PR_BODY,
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    done = _seed_finished_scenario_design(gh_live, owner, repo, ctx["pr"].number, level)
    _start(gh_live, owner, repo, ctx["pr"].number, level)

    # 実行: tester へのテスト実装タスクの割り当てを待つ
    def _assigned():
        data = issue(gh_live, owner, repo, ctx["pr"].number)
        names = label_names(data)
        if f"確認:{level['tester']}" not in names or f"確認:{level['writer']}" in names:
            return None
        return data

    data = wait_until(_assigned, timeout_sec=2400, message="テスト実装タスクの割り当て")

    # 検証: 割り当てコメントが tester 宛で、ページ名と commit 範囲の表を持つ
    posted = [
        c for c in comments_from(gh_live, owner, repo, ctx["pr"].number, level["writer"])
        if c.node_id != done.node_id
    ]
    assert posted, "テスト実装の割り当てコメントが投稿されていない"
    body = posted[-1].body or ""
    assert f"> to: @{level['tester']}" in body, "割り当ての宛先が tester でない"
    assert "設計図/シナリオ/" in body, f"E2E テスト化するシナリオのページ名がない: {body}"
    assert "commit" in body, f"各ページの commit 範囲がない: {body}"

    # 検証: ユーザー操作を求めていない
    assert "議論中" not in label_names(data), "議論中 が付与されている"
    assert not data.assignees, "assignee が設定されている"


def _run_retest(gh_live, owner, repo, level, factories, wait_until, sandbox):
    """正常シナリオ（再テストの実行）を実行して検証する。"""
    # 準備: fail 記録済み（実装 + レビュー済み）の結果表と、修正後に全 pass するテスト一式
    ctx = _setup(
        gh_live, owner, repo, level, factories,
        pr_body=STORY_PR_BODY_FAILED if level is SINGLE else EPIC_PR_BODY_FAILED,
        e2e_test=level["e2e_test"],
    )
    add_worktree(sandbox["local_path"], ctx["branch"])
    _seed_finished_scenario_design(gh_live, owner, repo, ctx["pr"].number, level)
    _start(gh_live, owner, repo, ctx["pr"].number, level)

    # 実行: 再実行 → 全 pass → 親への完了報告 まで進むのを待つ
    def _reported():
        if f"確認:{level['writer']}" in label_names(issue(gh_live, owner, repo, ctx["pr"].number)):
            return None
        parent_now = issue(gh_live, owner, repo, ctx["parent_number"])
        if f"確認:{level['conductor']}" not in label_names(parent_now):
            return None
        reports = comments_from(gh_live, owner, repo, ctx["parent_number"], level["writer"])
        return reports[-1] if reports else None

    completion = wait_until(_reported, timeout_sec=2400, message="再テスト後の全 pass 完了報告")

    # 検証: テスト結果表の結果列が全て ✅ に更新されている
    body = (issue(gh_live, owner, repo, ctx["pr"].number).body or "").replace("\r\n", "\n")
    rows = level["rows"](body)
    assert rows, "テスト結果表の行がない"
    for row in rows:
        assert "✅" in row, f"再実行後の結果列が ✅ で埋まっていない: {row}"

    # 検証: 実行したのは自分なのでテスト実行の行がチェックされ、全行チェック済みになる
    run = [
        line.strip() for line in body.splitlines()
        if line.strip().startswith("- [") and "テストを実行" in line
    ]
    assert run and all(line.startswith("- [x]") for line in run), (
        f"テスト実行のタスクが未チェック: {run}"
    )
    assert "- [ ]" not in body, f"タスク一覧に未チェックの行が残っている: {body}"

    # 検証: レビュー済みテストの再実行なので tester への割り当てを経由していない
    assert f"確認:{level['tester']}" not in _labeled_names(gh_live, owner, repo, ctx["pr"].number), (
        "再テストなのに tester への割り当てを経由している"
    )

    # 検証: 完了報告が conductor 宛で未解決のまま親 Issue に投稿されている
    assert f"> to: @{level['conductor']}" in (completion.body or ""), "完了報告の宛先が conductor でない"
    assert not server._is_minimized(completion.node_id), "完了報告が Resolve されている（受領は conductor）"


def test_normal_when_implement_start_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """テスト結果表が未記入のときのテスト実装タスクの割り当てを確認する（正常系・テスト実装の起動）。"""
    owner, repo = repo_ctx
    _run_implement_start(
        gh_live, owner, repo, SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_when_implement_start_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """テスト結果表が未記入のときのテスト実装タスクの割り当てを確認する（正常系・テスト実装の起動）。"""
    owner, repo = repo_ctx
    _run_implement_start(
        gh_live, owner, repo, COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_when_retest_single(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """fail 記録済みの表からの再実行と完了報告を確認する（正常系・再テストの実行）。"""
    owner, repo = repo_ctx
    _run_retest(
        gh_live, owner, repo, SINGLE,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )


def test_normal_when_retest_complex(
    monitor, gh_live, repo_ctx, epic_issue_factory, epic_pr_factory, draft_pr_factory,
    story_issue_factory, commit_file, wait_until, sandbox,
):
    """fail 記録済みの表からの再実行と完了報告を確認する（正常系・再テストの実行）。"""
    owner, repo = repo_ctx
    _run_retest(
        gh_live, owner, repo, COMPLEX,
        _factories(epic_issue_factory, epic_pr_factory, draft_pr_factory, story_issue_factory, commit_file),
        wait_until, sandbox,
    )
